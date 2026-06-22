"""试算凭证（quote token）签发与校验。

职责：
- 在真正发起扣费前，先把「本次生成需扣多少积分」结果以短期 JWT 形式交给客户端，
  客户端在确认扣费请求中回带该 token，服务端据此校验「试算结果未被篡改、用户一致、未过期」。

设计要点：
- 与登录态 access/refresh token **完全独立**：使用专属 payload 类型 `points_quote`，
  专属异常 `QuoteTokenError`，不复用 `app/core/security.py` 的任何函数。
  复用 `settings.jwt_secret_key` / `settings.jwt_algorithm` 仅作签名密钥复用，
  通过 `type` 字段做令牌隔离。
- 过期时间由 `settings.points_quote_expire_seconds` 控制，默认 300 秒，覆盖典型「试算→确认」窗口。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import settings

# 本模块专属的 payload 类型标记，用于和 access/refresh token 区分。
QUOTE_TOKEN_TYPE = "points_quote"


class QuoteTokenError(Exception):
    """试算凭证解析或校验失败（签名无效、已过期、类型不符、用户不符等）。"""


def hash_quote_params(params: dict) -> str:
    """对试算入参做稳定 SHA-256 哈希。

    排序键 + 紧凑 JSON，保证「同内容不同插入顺序」产出相同哈希；
    用于 quote token 中绑定参数（`QuoteClaims.params_hash`），防止客户端篡改计价入参。

    为什么放在本模块：它仅服务于 quote token 的参数指纹生成，与计价（pricing）逻辑无关，
    归属此处以保持内聚——阅读 quote token 流程时即可就近看到载荷如何构造。
    """
    import hashlib
    import json

    payload = json.dumps(
        params,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QuoteClaims:
    """试算凭证载荷数据载体（内部 DTO，不落库）。"""

    user_id: str
    business_type: str
    model_id: str
    params_hash: str
    required_points: int


def create_quote_token(claims: QuoteClaims) -> str:
    """将试算结果签发为短期 JWT。

    payload 固定包含：`type`、`sub`、`business_type`、`model_id`、
    `params_hash`、`required_points`、`iat`、`exp`。
    有效期读取 `settings.points_quote_expire_seconds`。
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "type": QUOTE_TOKEN_TYPE,
        "sub": claims.user_id,
        "business_type": claims.business_type,
        "model_id": claims.model_id,
        "params_hash": claims.params_hash,
        "required_points": claims.required_points,
        "iat": now,
        "exp": now + timedelta(seconds=settings.points_quote_expire_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_quote_token(token: str, *, expected_user_id: str) -> QuoteClaims:
    """解析并严格校验试算凭证。

    校验规则（任一不满足即抛 `QuoteTokenError`）：
    - 签名有效且未过期（PyJWT 自动校验 `exp`）；
    - `type == "points_quote"`（拒绝 access/refresh 等其他令牌）；
    - `sub == expected_user_id`（防止用户 A 使用用户 B 的试算结果）。
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise QuoteTokenError(str(exc)) from exc

    if payload.get("type") != QUOTE_TOKEN_TYPE:
        raise QuoteTokenError(f"unexpected token type: {payload.get('type')!r}")

    if payload.get("sub") != expected_user_id:
        raise QuoteTokenError("token subject does not match expected user")

    return QuoteClaims(
        user_id=str(payload["sub"]),
        business_type=str(payload["business_type"]),
        model_id=str(payload["model_id"]),
        params_hash=str(payload["params_hash"]),
        required_points=int(payload["required_points"]),
    )
