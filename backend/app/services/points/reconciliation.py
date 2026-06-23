"""积分冻结补偿服务：定时扫描逃逸的未结算冻结流水并按任务终态补消费/解冻。

为什么存在（设计定位）：
    正常流程下 `settle_task_billing_sync` / `settle_task_billing_async` 会在任务终态时
    立即消费或解冻冻结积分。但存在若干"逃逸"路径会让冻结流水长期悬挂：
      - worker 进程崩溃（SIGKILL/OOM）导致 finally 钩子未执行；
      - asyncio 事件循环关闭竞态（同步结算路径异常被吞）；
      - 同步计费调用崩溃后残留 freeze 但无 GenerationTask；
      - 任务记录被外部删除后冻结流水无人结算。
    本模块是这些路径的"兜底"补偿器，由 Celery Beat 每 5 分钟调度一次。

幂等保证：
    `consume_frozen` / `unfreeze_frozen` 均基于 `(billing_id, type)` 唯一约束幂等，
    且在 Redis 用户锁内提交。重复扫描同一冻结流水不会产生重复入账。

容错保证：
    单条流水的处理失败（异常或 BillingStateError 互斥竞态）被记录并跳过，
    不阻断同批其余条目。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.points import PointTransaction, PointTransactionType
from app.models.task import GenerationTask, GenerationTaskStatus
from app.services.points.ledger import consume_frozen, unfreeze_frozen

logger = logging.getLogger(__name__)


async def reconcile_stale_freezes(
    db: AsyncSession,
    *,
    batch_size: int | None = None,
    min_age_seconds: int | None = None,
) -> int:
    """扫描超过阈值的未结算冻结流水，按对应任务终态补消费/解冻；返回处理条数。

    参数：
        db: 用于扫描读与账本写的异步会话。账本操作内部自带 Redis 锁 + commit，
            因此扫描读可能看到 stale 行——这无妨，因为每行都会重新校验结算状态，
            且账本幂等。
        batch_size: 单批扫描上限；None 时取 `settings.points_reconcile_batch_size`。
        min_age_seconds: 冻结被视为"过期"的最小年龄（秒）；None 时取
            `settings.points_reconcile_min_age_seconds`。

    返回：本批真正执行了 consume / unfreeze 的条目数（跳过与保持冻结的不计入）。

    容错：单条异常被 `logger.exception` 记录后继续，避免一条坏数据阻断全批。
    """
    bs = batch_size if batch_size is not None else settings.points_reconcile_batch_size
    age = min_age_seconds if min_age_seconds is not None else settings.points_reconcile_min_age_seconds
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=age)

    # 1. 分页扫描过期 freeze 流水（按 created_at 升序，便于稳定排错）
    freeze_rows = (
        await db.execute(
            select(PointTransaction)
            .where(
                PointTransaction.type == PointTransactionType.freeze,
                PointTransaction.created_at < cutoff,
            )
            .order_by(PointTransaction.created_at)
            .limit(bs)
        )
    ).scalars().all()

    processed = 0
    for frz in freeze_rows:
        # 失败分诊上下文：在 try 之前解析，确保 except 中一定可绑定。
        # 孤儿冻结（无对应任务）时保持 None，供日志按任务维度检索。
        task_id: str | None = None
        task_status: str | None = None
        try:
            # 2. 已结算（已有 consume 或 unfreeze）→ 幂等跳过
            settled = (
                await db.execute(
                    select(PointTransaction.id).where(
                        PointTransaction.billing_id == frz.billing_id,
                        PointTransaction.type.in_(
                            [PointTransactionType.consume, PointTransactionType.unfreeze]
                        ),
                    ).limit(1)
                )
            ).first()
            if settled:
                continue

            # 3. 查对应任务终态，按终态决定补消费 / 解冻 / 保持冻结
            task = (
                await db.execute(
                    select(GenerationTask)
                    .where(GenerationTask.billing_id == frz.billing_id)
                    .limit(1)
                )
            ).scalars().first()

            # 记录失败分诊上下文（孤儿冻结时保持 None）
            if task is not None:
                task_id = task.id
                task_status = task.status

            if task is None:
                # 孤儿冻结：同步调用崩溃未关联任务 / 任务被删除 → 解冻
                await unfreeze_frozen(
                    db,
                    user_id=frz.user_id,
                    billing_id=frz.billing_id,
                    remark="reconcile: orphan freeze",
                    created_by="system",
                )
            elif task.status == GenerationTaskStatus.succeeded:
                await consume_frozen(db, user_id=frz.user_id, billing_id=frz.billing_id, created_by="system")
            elif task.status in (GenerationTaskStatus.failed, GenerationTaskStatus.cancelled):
                # task.status 列为 String(32)，读回为纯字符串。
                # GenerationTaskStatus 是 str,Enum，直接 ==/in 比较即可
                # （str-Enum 按字符串值比较，对纯字符串与枚举成员都成立），
                # 因此无需 isinstance/.value 防御。remark 直接用读回的字符串。
                await unfreeze_frozen(
                    db,
                    user_id=frz.user_id,
                    billing_id=frz.billing_id,
                    remark=f"reconcile: task {task.status}",
                    created_by="system",
                )
            else:
                # pending / running / streaming → 任务仍在跑，保持冻结
                continue
            processed += 1
        except Exception:  # noqa: BLE001 - 兜底补偿必须对单条坏数据容错
            # 兜底上下文：失败时记录任务 id 与终态（孤儿冻结时为 None），
            # 便于运维按任务维度分诊。注意 task_id/task_status 必须在 try
            # 之前解析，否则 except 中作用域变量可能未绑定。
            logger.exception(
                "reconcile freeze failed: billing_id=%s task_id=%s status=%s",
                frz.billing_id,
                task_id,
                task_status,
            )
            # 释放账本内部 SELECT ... FOR UPDATE 取得的行锁并重置事务快照。
            # 否则 BillingStateError（与正常结算竞态）等异常会让行锁与 stale
            # 快照延续到本批后续行，在 MySQL REPEATABLE READ 下污染后续处理。
            # 账本幂等，下一 Beat 周期会重新覆盖被跳过的行。
            await db.rollback()
            continue
    return processed


__all__ = ["reconcile_stale_freezes"]
