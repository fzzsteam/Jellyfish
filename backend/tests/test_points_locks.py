"""Redis 原子用户锁（积分账户并发控制）的契约测试。

校验内容：
- 锁键名固定为 `points:user:{user_id}`。
- 抢锁走 `SET key token NX PX ttl` 语义（互斥）。
- 释放使用「比较 token 再删除」的 Lua 脚本，避免误删他人持有的锁。
- 抢锁超时必须抛出 `PointsOperationBusyError`，且不得绕过 Redis（即 Redis 未授权时操作不得继续）。
"""

from __future__ import annotations

import asyncio

import pytest
from fakeredis.aioredis import FakeRedis

from app.services.points.locks import LOCK_KEY_PREFIX, PointsOperationBusyError, RedisUserLock


def _client() -> FakeRedis:
    """构造独立的 fakeredis 异步客户端，确保测试间状态隔离。"""
    return FakeRedis()


@pytest.mark.asyncio
async def test_lock_key_format_is_points_user() -> None:
    """锁键必须为 `points:user:{user_id}`，便于运维排查与监控。"""
    client = _client()
    try:
        lock = RedisUserLock(client, "u123")
        assert lock.key == f"{LOCK_KEY_PREFIX}u123"
        token = await lock.acquire()
        assert token is not None
        # 键确实被写入 Redis
        keys = await client.keys("*")
        assert lock.key.encode() in keys or lock.key in keys
        await lock.release(token)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_acquire_returns_token_and_second_lock_times_out() -> None:
    """同一用户第二次抢锁必须超时并抛 PointsOperationBusyError。"""
    client = _client()
    try:
        lock1 = RedisUserLock(client, "u1", wait_ms=100)
        lock2 = RedisUserLock(client, "u1", wait_ms=100)
        token = await lock1.acquire()
        assert isinstance(token, str) and len(token) > 0
        with pytest.raises(PointsOperationBusyError):
            await lock2.acquire()
        await lock1.release(token)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_release_with_correct_token_allows_reacquire() -> None:
    """正确 token 释放后，键被删除，后续抢锁可以成功。"""
    client = _client()
    try:
        lock = RedisUserLock(client, "u2")
        token = await lock.acquire()
        ok = await lock.release(token)
        assert ok == 1
        # 释放后键不存在
        exists = await client.exists(lock.key)
        assert exists == 0
        # 再次抢锁应成功
        token2 = await lock.acquire()
        assert token2 is not None
        await lock.release(token2)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_release_with_wrong_token_does_not_delete() -> None:
    """错误 token 释放不得删除键（防止误删他人持有的锁）。"""
    client = _client()
    try:
        lock = RedisUserLock(client, "u3")
        token = await lock.acquire()
        wrong = "wrong-token-value"
        ok = await lock.release(wrong)
        assert ok == 0
        # 键仍然存在
        exists = await client.exists(lock.key)
        assert exists == 1
        await lock.release(token)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_context_manager_raises_on_busy_and_does_not_bypass_redis() -> None:
    """作为上下文管理器使用：被占用时抛错，且绝不会进入受保护代码块。"""
    client = _client()
    try:
        holder = RedisUserLock(client, "u4")
        token = await holder.acquire()
        assert token is not None

        entered = False
        challenger = RedisUserLock(client, "u4", wait_ms=100)
        with pytest.raises(PointsOperationBusyError):
            async with challenger:
                entered = True  # 不应执行到这里
        assert entered is False, "Redis 未授权时不得进入受保护区域"

        await holder.release(token)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_context_manager_acquires_and_releases() -> None:
    """正常路径：进入上下文即持锁，退出后释放。"""
    client = _client()
    try:
        lock = RedisUserLock(client, "u5")
        async with lock:
            # 上下文内键存在
            exists = await client.exists(lock.key)
            assert exists == 1
        # 退出后键已被释放
        exists = await client.exists(lock.key)
        assert exists == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_busy_error_carries_user_id() -> None:
    """PointsOperationBusyError 应携带 user_id，便于上层定位。"""
    client = _client()
    try:
        lock1 = RedisUserLock(client, "u6")
        token = await lock1.acquire()
        lock2 = RedisUserLock(client, "u6", wait_ms=50)
        with pytest.raises(PointsOperationBusyError) as exc_info:
            await lock2.acquire()
        assert exc_info.value.user_id == "u6"
        await lock1.release(token)
    finally:
        await client.aclose()
