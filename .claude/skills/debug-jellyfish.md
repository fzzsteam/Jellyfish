---
name: debug-jellyfish
description: 排查 Jellyfish（AI 短剧工作台，FastAPI+Celery+MySQL+Redis）问题时使用。用户贴报错或描述问题（积分对不上、任务卡住、生成失败、连不上、行为异常等）时，按 4 步流程排查：探测环境 → 症状分流 → 取证 → 定位根因。只读取证，绝不臆测；数据库连接走 backend/.env 的 DATABASE_URL，不假设端口。
---

# debug-jellyfish — Jellyfish 问题排查

给 AI 用的项目排查流程。用户报错/报问题时**先取证再下结论**，套用 systematic-debugging 纪律（取证 → 假设 → 验证），禁止在取证前下结论。

## 🔒 安全红线（排查前必读）

- **数据库只读**：仅 `SELECT` / `SHOW` / `DESC` / `EXPLAIN`；禁止 `INSERT` / `UPDATE` / `DELETE` / `DROP` / `ALTER` / `CREATE` 等任何写或 DDL。
- **只查不改**：不修改 `.env` / 配置 / Celery 任务；Redis 只 `GET` / `KEYS`，不 `SET` / `DEL`。
- **凭证不外泄**：DB 密码只用于连接，不写入回复、提交或 skill 正文。

## Step 0 · 探测取证环境（每次排查最先做）

产出「取证上下文」：库连接（含端口）+ 日志获取方式 + redis/celery 入口。后续所有取证复用此上下文。

### 0.1 解析数据库连接（端口不要假设）

```bash
python3 - <<'PY'
import re
from pathlib import Path
url=next((l.split('=',1)[1].strip() for l in Path('backend/.env').read_text().splitlines() if l.startswith('DATABASE_URL=')),'')
scheme=url.split('://')[0]
print('engine=', 'mysql' if 'mysql' in scheme else ('sqlite' if 'sqlite' in scheme else scheme))
m=re.match(r'^[^:]+://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)$', url)
print('user=%s host=%s port=%s db=%s' % (m.group(1),m.group(3),m.group(4) or '3306',m.group(5))) if m else print('url=', url)
PY
```

实测输出（mysql + 方式 A）：

```
engine= mysql
user=jellyfish host=localhost port=3307 db=jellyfish
```

> 端口是 **3307**，不是默认 3306。后续 mysql 命令一律用这里解析出的 `port`。`engine=sqlite` 时改用 `sqlite3 backend/jellyfish.db`。

### 0.2 探测启动方式（决定日志怎么取）

```bash
docker ps --format '{{.Names}} {{.Status}}' | rg -i 'mysql|redis|rustfs|backend|celery'
pgrep -af 'uvicorn app.main|celery -A|celery worker' | rg -v 'pgrep|/bin/(zsh|bash)'
```

判断规则：

- `docker ps` 命中 `backend` / `celery-worker` → **方式 B（全 docker）**，日志走 `docker logs <容器名>` 或 `docker compose logs`。
- 仅 infra 容器（`mysql` / `redis` / `rustfs`）+ `pgrep` 命中 uvicorn/celery → **方式 A（本地服务）**，日志在宿主机进程 stdout（AI 抓不到 → 需让用户贴报错，或复现时重定向到文件再读）。
- `pgrep` 无 celery → **celery 未启动**，异步任务（生成、积分对账）不执行，常是「任务一直 pending」的根因。

> 本机 `docker compose -f ...` 子命令不可用，统一用 `docker ps` / `docker logs`。

## Step 1 · 症状分流（用户贴错误/描述问题 → 归类 → 决定先取证哪个）

| 症状 | 先取证 |
|---|---|
| 报错 / 异常 / 5xx / 堆栈 | 日志（按 Step 0 方式） |
| 数据对不上（积分 / 状态 / 数量） | 数据库只读查表 |
| 任务卡住 / 一直 pending | `generation_tasks` 表 + Celery 队列 + Redis 锁 |
| 连不上 / 配置 / 环境 | `backend/.env` + compose + `app/config.py` |
| 行为异常无报错 | 读对应 service/chain 源码理解逻辑 |
| 前端异常 | chrome-devtools MCP 看 console/network |

## Step 2 · 取证命令（复用 Step 0 上下文）

- **数据库（只读，端口取自 0.1，密码用 MYSQL_PWD 不进进程列表）**：

```bash
PASS=$(python3 -c "import re,pathlib;u=next(l for l in pathlib.Path('backend/.env').read_text().splitlines() if l.startswith('DATABASE_URL='));print(re.match(r'[^:]+://[^:]+:([^@]+)@',u).group(1))")
MYSQL_PWD="$PASS" mysql -h 127.0.0.1 -P 3307 -u jellyfish jellyfish -e "SELECT ... LIMIT 50;"
```

- **日志**：
  - 方式 B：`docker logs --tail 200 <backend容器名>` 或 celery-worker 容器，`| rg -i '<关键词>'`
  - 方式 A：宿主机进程日志（需用户贴报错，或复现时重定向 `uv run uvicorn ... 2>&1 | tee /tmp/jf-api.log` 后再读）

- **Redis**：`redis-cli -h localhost -p 6379 KEYS 'points:user:*'`、`GET points:user:<uid>`

- **Celery**：
  - 方式 A：`cd backend && uv run celery -A app.core.celery_app:celery_app inspect active`
  - 方式 B：`docker exec <celery-worker容器> celery -A app.core.celery_app:celery_app inspect active`

<!-- BUILD ANCHOR -->