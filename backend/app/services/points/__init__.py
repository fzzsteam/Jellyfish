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


def __getattr__(name: str):  # noqa: D401
    """惰性导出 billing 层符号，避免与 ledger/pricing 形成循环导入。

    为什么用 PEP 562 `__getattr__` 而非顶层 `from billing import ...`：
    `billing.py` 顶层 `from app.services.points import (...)` 反向依赖本包的
    ledger/pricing/quote_tokens 符号；若本 `__init__.py` 在顶层再 import billing，
    会形成 `__init__ → billing → __init__`（部分初始化）的循环导入。改为按需解析即可
    让 billing.py 完成模块初始化后再被引用。
    """
    if name in {
        "settle_task_billing_async",
        "settle_task_billing_sync",
        "freeze_for_call",
        "run_billed_text_operation",
    }:
        from app.services.points import billing as _billing

        return getattr(_billing, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    "settle_task_billing_async",
    "settle_task_billing_sync",
    "freeze_for_call",
    "run_billed_text_operation",
]
