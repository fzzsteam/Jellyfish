"""密码哈希与 JWT 令牌的生成、校验。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.config import settings

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """JWT 解析或校验失败（签名无效、已过期、类型不匹配等）。"""


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """校验明文密码与已存储哈希是否匹配。"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(*, user_id: str, token_version: int, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "token_version": token_version,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: str, token_version: int) -> str:
    """生成短期 access token（默认 15 分钟）。"""
    return _create_token(
        user_id=user_id,
        token_version=token_version,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(*, user_id: str, token_version: int) -> str:
    """生成长期 refresh token（默认 7 天）。"""
    return _create_token(
        user_id=user_id,
        token_version=token_version,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """解析并校验 JWT，类型不匹配或签名/过期校验失败均抛出 `TokenError`。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError(f"unexpected token type: {payload.get('type')!r}")
    return payload
