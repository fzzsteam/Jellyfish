"""积分相关 Celery 任务入口。

当前职责：
- `reconcile_stale_freezes`：由 Celery Beat 每 5 分钟调度，补偿逃逸的冻结积分流水。
  依赖任务终态判断如何结算，因此需要 tasks.reconcile_stale_generation_tasks
  先把僵死任务标记为 failed，否则冻结会一直保持"任务仍在跑"而不会被处理。

设计说明：
    Celery 任务本身是同步函数（在 prefork 子进程运行），通过 `asyncio.run` 驱动
    异步补偿核心 `reconcile_stale_freezes_async`（即 reconciliation 模块的同名函数）。
    这里用别名导入避免与 Celery task 名冲突。
"""

from __future__ import annotations

import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.db import async_session_maker
from app.services.points.reconciliation import (
    reconcile_stale_freezes as reconcile_stale_freezes_async,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="points.reconcile_stale_freezes")
def reconcile_stale_freezes() -> None:
    """Celery Beat 定时补偿未结算冻结积分的同步入口。

    在独立事件循环中驱动异步核心；失败仅记录日志，不抛出（Beat 会按调度重试）。
    """
    async def _run() -> int:
        async with async_session_maker() as db:
            return await reconcile_stale_freezes_async(db)

    try:
        processed = asyncio.run(_run())
        if processed:
            logger.info("reconcile_stale_freezes processed %d freeze(s)", processed)
    except Exception:  # noqa: BLE001 - Beat 调度任务不应因单次异常退出
        logger.exception("reconcile_stale_freezes crashed")


__all__ = ["reconcile_stale_freezes"]
