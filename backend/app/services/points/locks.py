"""积分账户的 Redis 原子锁。

为什么存在：
    积分账户（`UserPoints`）是热点资源，并发下单/扣费/退款都会改写它。SQL 层的
    `SELECT ... FOR UPDATE` 在 MySQL 上可以行锁，但在 SQLite（测试）上是 no-op，
    无法阻止应用层竞态。引入一层 Redis 分布式锁做互斥，保证「同一用户的账户变更」
    在任意时刻只有一个执行流进行，从而避免超扣、余额错乱。

锁语义：
    - 锁键固定为 `points:user:{user_id}`。
    - 抢锁 = `SET key token NX PX ttl`（仅当键不存在时写入，并设置毫秒级 TTL 防止持锁进程崩溃后死锁）。
    - 释放 = Lua 脚本「读取值，等于 token 才删除」，避免误删他人持有的锁。
    - 超时未抢到锁抛 `PointsOperationBusyError`，绝不绕过 Redis 继续执行。

注意：持锁代码块内部完成 DB 变更并 `commit()` 后再释放锁，保证「锁覆盖整个临界区」。
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅用于类型注解，避免运行期对 redis 的硬依赖
    import redis.asyncio as aioredis  # noqa: F401

from app.config import settings

# 模块日志器：`__aexit__` 中释放锁失败时记录告警，便于排查 Redis 抖动等问题。
logger = logging.getLogger(__name__)

# 锁键前缀：与 user_id 拼接形成完整键名 `points:user:{user_id}`。
LOCK_KEY_PREFIX = "points:user:"

# 释放锁的 Lua 脚本：仅当键的值等于持有的 token 时才删除，保证不会误删别人的锁。
# 返回 1 表示删除成功（即成功释放），0 表示键不存在或 token 不匹配。
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class PointsOperationBusyError(Exception):
    """抢锁超时：同一用户的账户变更正在被其他执行流处理。

    携带 `user_id` 便于上层 API 据此返回「请稍后重试」类响应。此类抛出意味着
    Redis 明确告知「未获得锁」，受保护操作绝对不会继续执行。
    """

    def __init__(self, user_id: str, *, key: str, wait_ms: int) -> None:
        self.user_id = user_id
        self.key = key
        self.wait_ms = wait_ms
        super().__init__(
            f"points lock busy for user_id={user_id} (key={key}, waited={wait_ms}ms)"
        )


class RedisUserLock:
    """单个用户积分账户的 Redis 互斥锁（异步上下文管理器）。

    使用方式：
        async with RedisUserLock(client, user_id):
            ...  # 临界区：DB 读改写 + commit

    参数从 `settings` 读取默认值（TTL / 最长等待 / 退避上限），也可在构造时显式覆盖，
    方便测试在不改全局配置的情况下调小等待时间。
    """

    def __init__(
        self,
        redis_client: "aioredis.Redis",
        user_id: str,
        *,
        ttl_ms: int | None = None,
        wait_ms: int | None = None,
        backoff_ms: int | None = None,
    ) -> None:
        self._client = redis_client
        self._user_id = user_id
        # 锁 TTL：持锁进程崩溃后，键也会在 TTL 内自动过期，避免死锁。
        self._ttl_ms = ttl_ms if ttl_ms is not None else settings.points_lock_ttl_ms
        # 最长抢锁等待：超过即放弃并抛错，防止调用方无限挂起。
        self._wait_ms = wait_ms if wait_ms is not None else settings.points_lock_wait_ms
        # 指数退避上限：抢锁失败后睡眠一段时间再重试，上限防止打满 CPU。
        self._backoff_ms = (
            backoff_ms if backoff_ms is not None else settings.points_lock_retry_max_backoff_ms
        )
        # 当前持有的 token（抢锁成功后写入，释放时校验）。
        self._token: str | None = None

    @property
    def user_id(self) -> str:
        """锁归属的用户 ID。"""
        return self._user_id

    @property
    def key(self) -> str:
        """Redis 键名：`points:user:{user_id}`。"""
        return f"{LOCK_KEY_PREFIX}{self._user_id}"

    async def acquire(self) -> str:
        """抢锁：成功返回 token；在等待窗口内始终失败则抛 PointsOperationBusyError。

        实现：`SET key token NX PX ttl` 循环重试，失败时指数退避（上限 backoff_ms），
        累计等待超过 wait_ms 即放弃。token 使用 `secrets.token_urlsafe(24)` 保证
        不可预测，使「比较 token 再删除」的释放逻辑安全。
        """
        token = secrets.token_urlsafe(24)
        deadline = time.monotonic() + (self._wait_ms / 1000.0)
        sleep_ms = 10  # 初始退避 10ms
        while True:
            # SET NX PX：键不存在才写入，并设置毫秒 TTL。返回 True 表示抢到。
            ok = await self._client.set(self.key, token, nx=True, px=self._ttl_ms)
            if ok:
                self._token = token
                return token
            # 未抢到：检查是否还有等待预算。
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # 超时：Redis 明确未授权，抛错让上层放弃，绝不绕过锁继续。
                raise PointsOperationBusyError(
                    self._user_id, key=self.key, wait_ms=self._wait_ms
                )
            # 退避后再试，退避时长受 remaining 与 backoff 上限双重约束。
            delay = min(sleep_ms, self._backoff_ms, int(remaining * 1000)) / 1000.0
            await asyncio.sleep(delay)
            sleep_ms = min(sleep_ms * 2, self._backoff_ms)

    async def release(self, token: str | None = None) -> int:
        """释放锁：仅当键的值等于 token 时删除。返回 1 成功 / 0 未释放。

        显式传入 token 便于测试验证「错误 token 不会误删」。默认使用抢锁时记录的 token。
        """
        actual = token if token is not None else self._token
        if actual is None:
            return 0
        # 执行 Lua 脚本：redis-py 会缓存脚本，重复调用走 EVALSHA。
        result = await self._client.eval(_RELEASE_SCRIPT, 1, self.key, actual)
        self._token = None
        return int(result)

    async def __aenter__(self) -> "RedisUserLock":
        """进入临界区：抢锁。失败抛 PointsOperationBusyError，受保护代码不会执行。"""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401 - 标准签名
        """退出临界区：释放锁，但绝不掩盖受保护代码块抛出的业务异常。

        若 `release()` 自身失败（Redis 抖动、Lua 报错），分两种情况：
          - 受保护块原本无异常 → 直接抛 release 错误，避免静默状态错乱；
          - 受保护块已有异常（如 InsufficientPointsError）→ 记日志后吞掉 release 错误，
            让原始业务异常继续传播；锁由 TTL 兜底回收，不会因释放失败而永久占用。
        """
        try:
            await self.release()
        except Exception:  # noqa: BLE001 — 锁有 TTL 兜底；绝不掩盖原始业务异常
            if exc is None:
                # 无原始异常：抛出 release 错误本身，避免静默损坏状态。
                raise
            # 有原始异常：记录后吞掉 release 错误，由 TTL 回收锁，原始异常继续传播。
            logger.warning("释放积分锁失败，将由 TTL 兜底回收", exc_info=True)
