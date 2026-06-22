"""通用模型混入。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class TimestampMixin:
    """created_at / updated_at 时间戳混入。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserOwnedMixin:
    """为业务表提供 `user_id` 归属外键。

    存在意义：项目要求项目/资产/配置/任务等按用户严格隔离，所有归属表统一通过本混入
    携带指向 `users.id` 的外键，避免在每个模型里重复声明。`ondelete="CASCADE"` 保证
    删除用户时其全部业务数据级联清除。新建库 `create_all` 直接生成 NOT NULL 列；存量库
    由 sql/009 先加 NULL 列回填后再收紧为 NOT NULL。
    """

    @declared_attr
    def user_id(cls) -> Mapped[str]:  # noqa: N805
        return mapped_column(
            String(64),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="归属用户 ID",
        )
