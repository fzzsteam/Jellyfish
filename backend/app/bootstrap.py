"""应用级注册入口：统一初始化供应商能力、任务执行器与初始管理员账号（均幂等）。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_password
from app.models.user import User


def bootstrap_all_registries() -> None:
    """启动时或惰性路径中调用一次即可；顺序固定为 provider 先于 task adapter。"""
    from app.core.tasks.bootstrap import bootstrap_task_adapters
    from app.services.llm.provider_bootstrap import bootstrap_builtin_providers

    bootstrap_builtin_providers()
    bootstrap_task_adapters()


async def seed_initial_admin(db: AsyncSession) -> None:
    """若数据库中尚无管理员账号，按配置创建初始管理员（幂等）。

    `INITIAL_ADMIN_PASSWORD` 未设置且表为空时：记录 ERROR 并拒绝启动，避免默认弱密码。
    """
    existing = await db.execute(select(User).where(User.is_admin.is_(True)))
    if existing.scalars().first() is not None:
        return

    if not settings.initial_admin_password:
        raise RuntimeError(
            "INITIAL_ADMIN_PASSWORD is not set; refusing to start without an initial admin account"
        )

    admin = User(
        id=str(uuid.uuid4()),
        username=settings.initial_admin_username,
        hashed_password=hash_password(settings.initial_admin_password),
        is_admin=True,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
