"""管理员用户管理业务逻辑：创建、列表、查询、修改（重置密码/启停/角色）。

存在意义：把用户 CRUD 与隔离/审计相关的不变量（用户名唯一、改密或禁用时递增
token_version 以即时吊销旧 token、不允许禁用/降级最后一个管理员）收敛到 service，
路由层只收参鉴权。
"""

from __future__ import annotations

import secrets
import string
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.points import UserPoints
from app.models.user import User


class UsernameExistsError(Exception):
    """用户名已存在。"""


class UserNotFoundError(Exception):
    """目标用户不存在。"""


class LastAdminError(Exception):
    """不允许禁用或降级最后一个启用中的管理员（避免系统失去管理员）。"""


async def create_user(db: AsyncSession, *, username: str, password: str, is_admin: bool) -> User:
    """创建用户；用户名重复抛 `UsernameExistsError`。"""
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none() is not None:
        raise UsernameExistsError(username)
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        hashed_password=hash_password(password),
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    # 同事务内初始化积分账户（余额/冻结均为 0），避免用户创建后缺失积分账户导致后续试算/扣费兜底创建。
    db.add(UserPoints(user_id=user.id, balance=0, frozen=0))
    await db.refresh(user)
    return user


async def list_users(db: AsyncSession, *, page: int, page_size: int) -> tuple[list[User], int]:
    """分页列出全部用户（按创建时间倒序）。"""
    total = await db.scalar(select(func.count()).select_from(User))
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_user(db: AsyncSession, user_id: str) -> User:
    """按 ID 查询用户；不存在抛 `UserNotFoundError`。"""
    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    return user


async def _active_admin_count(db: AsyncSession) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True), User.is_active.is_(True))
        )
        or 0
    )


async def update_user(
    db: AsyncSession,
    user_id: str,
    *,
    password: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
) -> User:
    """修改用户：重置密码 / 启停 / 角色。

    - 重置密码或禁用账号时递增 `token_version`，使该用户已签发的 token 立即失效。
    - 不允许把最后一个启用中的管理员禁用或降级（`LastAdminError`），避免系统失去管理员。
    """
    user = await get_user(db, user_id)

    removing_last_admin = (
        user.is_admin
        and user.is_active
        and await _active_admin_count(db) <= 1
        and (is_active is False or is_admin is False)
    )
    if removing_last_admin:
        raise LastAdminError(user_id)

    bump = False
    if password is not None:
        user.hashed_password = hash_password(password)
        bump = True
    if is_active is not None:
        if user.is_active and not is_active:
            bump = True
        user.is_active = is_active
    if is_admin is not None:
        user.is_admin = is_admin
    if bump:
        user.token_version += 1

    await db.flush()
    await db.refresh(user)
    return user


# 临时密码字符集：排除 0/O/1/l/I 等肉眼易混字符，便于人工抄写或口述。
_TEMP_PASSWORD_ALPHABET = "".join(
    c for c in (string.ascii_letters + string.digits) if c not in "0O1lI"
)


def _generate_temporary_password(length: int = 12) -> str:
    """生成易读的随机临时密码（使用密码学安全的 secrets.choice）。"""
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))


async def reset_password(db: AsyncSession, user_id: str) -> tuple[User, str]:
    """管理员重置目标用户密码：生成随机临时密码并递增 token_version。

    目标不存在抛 `UserNotFoundError`。返回 (user, temporary_password)，
    临时密码仅本次返回，调用方需一次性展示给管理员。
    """
    user = await get_user(db, user_id)
    temporary_password = _generate_temporary_password()
    user.hashed_password = hash_password(temporary_password)
    user.token_version += 1
    await db.flush()
    await db.refresh(user)
    return user, temporary_password
