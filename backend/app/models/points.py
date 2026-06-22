"""积分计费相关 ORM 模型。

定义用户积分余额、积分流水两类聚合，作为后续积分扣费/冻结/回滚服务的持久化基础。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class PointTransactionType(str, Enum):
    """积分流水类型：覆盖积分账户的全部状态流转动作。

    - recharge: 充值（余额增加）
    - freeze: 冻结（下单时预占，余额不变，冻结额增加）
    - consume: 扣减（任务成功后从冻结额结算扣出，余额与冻结额同步减少）
    - unfreeze: 解冻（任务失败/取消时释放冻结额）
    """

    recharge = "recharge"
    freeze = "freeze"
    consume = "consume"
    unfreeze = "unfreeze"


class UserPoints(Base, TimestampMixin):
    """用户积分账户（每用户一行）。

    `balance` 为账户总额（含已冻结部分），`frozen` 为已冻结额；`available = balance - frozen`
    为可用额度。CHECK 约束保证：余额非负、冻结非负、冻结不超过余额。
    """

    __tablename__ = "user_points"

    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        unique=True,
        comment="用户 ID（主键，一行一用户）",
    )
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="积分余额")
    frozen: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="冻结积分")

    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_user_points_balance_nonneg"),
        CheckConstraint("frozen >= 0", name="ck_user_points_frozen_nonneg"),
        CheckConstraint("frozen <= balance", name="ck_user_points_frozen_le_balance"),
    )


class PointTransaction(Base, TimestampMixin):
    """积分流水（不可变 append-only 记录）。

    每条记录描述一次账户状态变更。`balance_after` / `frozen_after` 为变更后的账户快照，
    便于审计与对账。`(billing_id, type)` 唯一约束防止同一计费单据重复入账。
    """

    __tablename__ = "point_transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="流水 ID")
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="归属用户 ID",
    )
    type: Mapped[PointTransactionType] = mapped_column(
        String(32),
        nullable=False,
        comment="流水类型：recharge/freeze/consume/unfreeze",
    )
    amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="本次变更涉及的积分数量，符号随类型变化：recharge 支持正负（正为充值、负为扣减）；freeze/consume/unfreeze 为正数",
    )
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="变更后余额")
    frozen_after: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="变更后冻结额")
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="来源：system/manual/task/...",
    )
    billing_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="计费单据 ID（可空，非业务流程为 NULL）",
    )
    business_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="业务类型：image_generation/video_generation/...",
    )
    business_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="业务实体 ID（如生成任务 ID）",
    )
    model_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("models.id", ondelete="SET NULL"),
        nullable=True,
        comment="涉及的模型 ID（删除模型时置空，保留流水）",
    )
    pricing_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="下单时计价快照（JSON），用于历史对账不受调价影响",
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    created_by: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="操作人（删除用户时置空，保留流水）",
    )

    __table_args__ = (
        UniqueConstraint("billing_id", "type", name="uq_point_transactions_billing_type"),
        Index("ix_point_transactions_user_id_created_at", "user_id", "created_at"),
    )
