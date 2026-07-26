"""僵死 GenerationTask 对账 Celery 任务入口。

当前职责：
- `reconcile_stale_generation_tasks`：由 Celery Beat 每 5 分钟调度，把因 worker
  被硬杀死（Celery task_time_limit）而永久停留在 pending/running/streaming 的任务
  强制标记为 failed，详见 app.services.worker.task_reconciliation 中的设计说明。

设计说明：
    Celery 任务本身是同步函数（在 prefork 子进程运行），通过 `asyncio.run` 驱动
    异步核心 `reconcile_stale_generation_tasks`（即 task_reconciliation 模块的同名
    函数）。这里用别名导入避免与 Celery task 名冲突。
"""

from __future__ import annotations

import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.db import async_session_maker
from app.services.worker.task_reconciliation import (
    reconcile_stale_generation_tasks as reconcile_stale_generation_tasks_async,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.reconcile_stale_generation_tasks")
def reconcile_stale_generation_tasks() -> None:
    """Celery Beat 定时标记僵死任务为 failed 的同步入口。

    在独立事件循环中驱动异步核心；失败仅记录日志，不抛出（Beat 会按调度重试）。
    """
    async def _run() -> int:
        async with async_session_maker() as db:
            return await reconcile_stale_generation_tasks_async(db)

    try:
        processed = asyncio.run(_run())
        if processed:
            logger.warning("reconcile_stale_generation_tasks marked %d task(s) as failed", processed)
    except Exception:  # noqa: BLE001 - Beat 调度任务不应因单次异常退出
        logger.exception("reconcile_stale_generation_tasks crashed")


__all__ = ["reconcile_stale_generation_tasks"]
