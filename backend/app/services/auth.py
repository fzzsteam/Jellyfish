"""认证业务逻辑：登录校验、令牌签发与刷新。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import AccessTokenRead, TokenPairRead


class InvalidCredentialsError(Exception):
    """用户名或密码错误，或账号已被禁用。"""


class InvalidTokenError(Exception):
    """令牌无效、已过期或已被吊销。"""


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    """按 ID 查询用户。"""
    return await db.get(User, user_id)


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """按用户名查询用户。"""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def authenticate(db: AsyncSession, *, username: str, password: str) -> TokenPairRead:
    """校验用户名密码并签发令牌对；用户不存在/密码错误/账号禁用均报 `InvalidCredentialsError`。"""
    user = await get_user_by_username(db, username)
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("invalid username or password")
    return TokenPairRead(
        access_token=create_access_token(user_id=user.id, token_version=user.token_version),
        refresh_token=create_refresh_token(user_id=user.id, token_version=user.token_version),
    )


async def refresh_access_token(db: AsyncSession, *, refresh_token: str) -> AccessTokenRead:
    """用 refresh token 换取新的 access token；token 失效/已吊销均报 `InvalidTokenError`。"""
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise InvalidTokenError(str(exc)) from exc

    user = await get_user_by_id(db, payload["sub"])
    if user is None or not user.is_active or user.token_version != payload["token_version"]:
        raise InvalidTokenError("user inactive or token revoked")

    return AccessTokenRead(access_token=create_access_token(user_id=user.id, token_version=user.token_version))


async def change_password(
    db: AsyncSession, *, user_id: str, current_password: str, new_password: str
) -> User:
    """当前用户自助改密：校验旧密码后更新哈希并递增 token_version。

    旧密码不匹配抛 `InvalidCredentialsError`；改密即吊销已签发 token。
    """
    user = await get_user_by_id(db, user_id)
    if user is None or not verify_password(current_password, user.hashed_password):
        raise InvalidCredentialsError("current password is incorrect")
    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    await db.flush()
    await db.refresh(user)
    return user
