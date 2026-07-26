"""GenerationTask 孤儿任务对账：兜底处理被 worker 硬杀死后永久停留在
pending/running/streaming 状态、永远等不到终态的任务记录。

为什么存在（设计定位）：
    Celery 的 ``task_time_limit``（硬超时，见 app/core/celery_app.py）到点后直接对
    worker 子进程发 SIGKILL；SIGKILL 不给 Python 任何清理机会，
    ``AbstractWorkerTaskExecutor.run()`` 里的 ``except`` 分支不会执行，
    ``GenerationTask.status`` 永远停在 running，前端表现为“任务一直卡住不返回”。
    ``task_soft_time_limit`` 理论上会先抛出可被现有代码捕获的
    ``SoftTimeLimitExceeded``，但如果任务正阻塞在不可中断的 C 扩展调用里
    （例如卡住的 TLS 握手/读，对应一次没有 socket 超时的 LLM 供应商请求），
    该信号可能被吞掉，最终仍然落到硬 kill 这条路径。
    本模块由 Celery Beat 定时扫描超过对应超时阈值 + 宽限期仍未终结的任务，
    强制标记为 failed，避免任务本身、以及依赖任务终态才会解冻的积分冻结流水
    （见 app/services/points/reconciliation.py）永久悬挂。

幂等保证：
    只对仍处于非终态的行做一次 set_error + set_status(failed)；重复扫描到已被
    其他路径改写为终态的行会被下一轮查询自然排除，不会重复处理。

容错保证：
    单条记录处理失败被记录并跳过，不阻断同批其余记录。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.task_manager.stores import SqlAlchemyTaskStore
from app.core.task_manager.types import TaskStatus
from app.models.task import GenerationTask, GenerationTaskStatus

logger = logging.getLogger(__name__)


async def reconcile_stale_generation_tasks(
    db: AsyncSession,
    *,
    batch_size: int | None = None,
    min_age_seconds: int | None = None,
) -> int:
    """扫描长期停留在非终态的任务记录，强制标记为 failed；返回处理条数。

    参数：
        db: 用于扫描读与状态写入的异步会话。
        batch_size: 单批扫描上限；None 时取 `settings.stale_task_reconcile_batch_size`。
        min_age_seconds: 任务被视为"僵死"的最小无更新时长（秒）；None 时取
            `settings.stale_task_reconcile_min_age_seconds`（默认覆盖 Celery
            硬超时 4200s 并留出宽限期，正常任务不会触碰到）。
    """
    bs = batch_size if batch_size is not None else settings.stale_task_reconcile_batch_size
    age = min_age_seconds if min_age_seconds is not None else settings.stale_task_reconcile_min_age_seconds
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=age)

    stale_rows = (
        await db.execute(
            select(GenerationTask)
            .where(
                GenerationTask.status.in_(
                    [
                        GenerationTaskStatus.pending,
                        GenerationTaskStatus.running,
                        GenerationTaskStatus.streaming,
                    ]
                ),
                GenerationTask.updated_at < cutoff,
            )
            .order_by(GenerationTask.updated_at)
            .limit(bs)
        )
    ).scalars().all()

    store = SqlAlchemyTaskStore(db)
    processed = 0
    for row in stale_rows:
        try:
            await store.set_error(
                row.id,
                f"任务在 {row.status} 状态下超过 {age} 秒无更新，疑似 worker 被强制终止"
                "（如 Celery 硬超时/进程重启/OOM），系统自动标记失败，可重新发起",
            )
            await store.set_status(row.id, TaskStatus.failed)
            await db.commit()
            processed += 1
        except Exception:  # noqa: BLE001 - 兜底补偿必须对单条坏数据容错
            logger.exception("reconcile stale generation task failed: task_id=%s", row.id)
            await db.rollback()
            continue
    return processed


__all__ = ["reconcile_stale_generation_tasks"]
