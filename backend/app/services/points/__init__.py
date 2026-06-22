"""积分计费服务包。

对外稳定公开以下符号（后续任务据此做 `from app.services.points import ...`）：

- `calculate_points` / `UnsupportedResolutionError` / `hash_quote_params`：纯计价与参数哈希。
- `QuoteClaims` / `create_quote_token` / `decode_quote_token` / `QuoteTokenError`：试算凭证。
- 账本（ledger）：`get_points` / `freeze_points` / `consume_frozen` / `unfreeze_frozen` /
  `recharge` 及异常 `InsufficientPointsError` / `BillingStateError` / `PointsOperationBusyError`。
"""

from __future__ import annotations

from app.services.points.ledger import (
    BillingStateError,
    InsufficientPointsError,
    PointsOperationBusyError,
    consume_frozen,
    freeze_points,
    get_points,
    recharge,
    unfreeze_frozen,
)
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
    "BillingStateError",
    "InsufficientPointsError",
    "PointsOperationBusyError",
    "consume_frozen",
    "freeze_points",
    "get_points",
    "recharge",
    "unfreeze_frozen",
]
