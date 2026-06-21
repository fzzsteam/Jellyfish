"""数据库迁移执行脚本：按文件名顺序遍历执行 backend/sql/*.sql。

为什么用 Python 而非 `mysql < file`：
- 生产容器（combined.Dockerfile）未安装 mysql 命令行客户端，但自带 Python；
- 连接信息直接复用 settings.DATABASE_URL，无需单独配置账号密码。

幂等性：依赖每个 SQL 脚本自身的幂等设计（用 information_schema 探测列/约束是否存在
再决定是否执行 DDL），因此可重复执行，已应用的语句会跳过；多实例环境下重复执行也安全。

用法：
    cd backend
    uv run python apply_migrations.py        # 执行全部 sql/*.sql
    uv run python apply_migrations.py 009    # 仅执行文件名以 009 开头的脚本
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import aiomysql
from pymysql.constants import CLIENT
from sqlalchemy import make_url

from app.config import settings

SQL_DIR = Path(__file__).resolve().parent / "sql"


async def _apply_file(conn: aiomysql.Connection, path: Path) -> None:
    """读取单个 SQL 文件并以多语句模式执行；消费全部结果集避免 out-of-sync。"""
    sql = path.read_text(encoding="utf-8")
    if not sql.strip():
        print(f"  [skip] {path.name}: 空文件")
        return
    async with conn.cursor() as cur:
        await cur.execute(sql)
        # 多语句模式下，execute 只取第一条结果；剩余结果集必须逐个 nextset 消费干净，
        # 否则连接进入 "Commands out of sync" 状态，后续语句会失败。
        while await cur.nextset():
            pass


async def main(filter_prefix: str | None = None) -> int:
    """连接数据库并按序执行迁移；任一文件失败即停止，避免跳过有顺序依赖的前置脚本。"""
    url = make_url(settings.database_url)
    files = sorted(SQL_DIR.glob("*.sql"))
    if filter_prefix:
        files = [f for f in files if f.name.startswith(filter_prefix)]
    if not files:
        print(f"未找到要执行的 SQL 文件（目录={SQL_DIR}, 过滤={filter_prefix!r}）")
        return 0

    print(f"数据库: {url.drivername} {url.host}:{url.port or 3306}/{url.database}")
    print(f"待执行 {len(files)} 个: {[f.name for f in files]}\n")

    conn = await aiomysql.connect(
        host=url.host,
        port=url.port or 3306,
        user=url.username,
        password=url.password or "",
        db=url.database,
        charset="utf8mb4",
        autocommit=True,
        # 开启多语句 + 多结果集，才能一次执行含多条 ; 分隔语句的整份 SQL 文件
        client_flag=CLIENT.MULTI_STATEMENTS | CLIENT.MULTI_RESULTS,
    )
    try:
        for f in files:
            print(f"[apply] {f.name}")
            try:
                await _apply_file(conn, f)
            except Exception as exc:  # noqa: BLE001
                print(f"  [FAIL] {f.name}: {exc}")
                print("已停止：后续脚本未执行。修复后可重新运行（脚本幂等）。")
                return 1
            print(f"  [ok]   {f.name}")
        print("\n全部迁移执行完成。")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    prefix = sys.argv[1] if len(sys.argv) > 1 else None
    raise SystemExit(asyncio.run(main(prefix)))
