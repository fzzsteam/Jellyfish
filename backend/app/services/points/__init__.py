"""积分计费服务包。

对外稳定公开以下符号（后续任务据此做 `from app.services.points import ...`）：

- `calculate_points` / `UnsupportedResolutionError` / `hash_quote_params`：纯计价与参数哈希。
- `QuoteClaims` / `create_quote_token` / `decode_quote_token` / `QuoteTokenError`：试算凭证。
"""

from __future__ import annotations

from app.services.points.pricing import (
    UnsupportedResolutionError,
    calculate_points,
)
from app.services.points.quote_tokens import (
    QuoteClaims,
    QuoteTokenError,
    create_quote_token,
    decode_quote_token,
    hash_quote_params,
)

__all__ = [
    "UnsupportedResolutionError",
    "calculate_points",
    "hash_quote_params",
    "QuoteClaims",
    "create_quote_token",
    "decode_quote_token",
    "QuoteTokenError",
]
