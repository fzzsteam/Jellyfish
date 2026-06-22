"""积分试算与领域错误编排服务。

为什么存在：
    把「模型解析 → 计价 → 余额查询 → 试算凭证签发」这条链路收敛到一处，并对上层 API
    暴露统一的领域错误 `PointsDomainError`（携带稳定字符串 code、HTTP 状态码、结构化 data），
    避免 HTTPException 散落各处导致前端无法按稳定 code 分支。

职责边界：
    - 不直接读写积分账户状态（冻结/扣减/解冻/充值由 `ledger.py` 负责）。
    - 只做读侧的试算与查询；写侧的扣费/确认在后续任务复用 ledger。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import Model, ModelCategoryKey
from app.models.points import PointTransaction, PointTransactionType
from app.schemas.points import PointsQuoteResponse, PointsSummaryRead
from app.services.llm.resolver import get_default_model_by_category
from app.services.points import (
    UnsupportedResolutionError,
    calculate_points,
    create_quote_token,
    get_points,
    hash_quote_params,
)
from app.services.points.quote_tokens import QuoteClaims


class PointsDomainError(Exception):
    """积分领域错误：携带稳定字符串 code、HTTP 状态码与结构化 data。

    为什么不复用 HTTPException：
        HTTPException 的 detail 通常是裸字符串，无法承载结构化字段（available/required/shortfall、
        新试算结果等），且会被 main.py 的通用 HTTPException 处理器吞掉结构。本类独立于
        HTTPException，由 main.py 注册专属处理器序列化为 ApiResponse 信封，稳定 code 放在
        `data.error_code`，便于前端按 code 精确分支。
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code  # 稳定字符串：INSUFFICIENT_POINTS / POINTS_QUOTE_CHANGED / POINTS_OPERATION_BUSY / MODEL_NOT_OWNED
        self.message = message
        self.status_code = status_code
        self.data = data or {}


def build_insufficient_error(*, available: int, required: int, shortfall: int) -> PointsDomainError:
    """构造余额不足错误（HTTP 402），data 携带 available/required/shortfall。"""
    return PointsDomainError(
        code="INSUFFICIENT_POINTS",
        message="insufficient points",
        status_code=402,
        data={"available": available, "required": required, "shortfall": shortfall},
    )


def build_quote_changed_error(*, new_quote: dict[str, Any]) -> PointsDomainError:
    """构造试算已变更错误（HTTP 409），data 携带最新试算结果。

    为什么需要：用户持旧 quote_token 确认扣费时，若服务端按当前单价/参数重算的结果与 token 中
    required_points 不一致，必须拒绝并回带最新试算，让前端重新确认。Task 5/6 的扣费确认会触发。
    """
    return PointsDomainError(
        code="POINTS_QUOTE_CHANGED",
        message="points quote has changed, please re-quote",
        status_code=409,
        data=dict(new_quote),
    )


def build_busy_error(*, user_id: str) -> PointsDomainError:
    """构造账户操作繁忙错误（HTTP 503），提示稍后重试。"""
    return PointsDomainError(
        code="POINTS_OPERATION_BUSY",
        message="points operation busy, please retry later",
        status_code=503,
        data={"user_id": user_id},
    )


def build_model_not_owned_error(*, model_id: str, user_id: str) -> PointsDomainError:
    """构造模型归属校验失败错误（HTTP 403），拒绝借用他人模型计价。

    为什么需要：`resolver.get_model_by_category` 不会校验显式 model_id 是否归属当前用户
    （模型按用户严格隔离），试算必须显式补这道校验，否则用户可借用他人模型的单价试算。
    """
    return PointsDomainError(
        code="MODEL_NOT_OWNED",
        message=f"model {model_id} does not belong to user {user_id}",
        status_code=403,
        data={"model_id": model_id, "user_id": user_id},
    )


async def quote_points(
    db: AsyncSession,
    *,
    user_id: str,
    business_type: str,
    category: ModelCategoryKey,
    model_id: str | None = None,
    duration_seconds: int | None = None,
    resolution: str | None = None,
    generation_count: int = 1,
) -> PointsQuoteResponse:
    """试算：解析模型 → 计价 → 查余额 → 签发 quote_token。

    - 显式 `model_id`：先按 id 取 Model，校验归属（`model.user_id == user_id`）与类别匹配。
    - 默认模型：调用 `get_default_model_by_category`，无默认配置时让其抛 503 HTTPException
      （属配置错误，由通用 HTTPException 处理器兜底即可）。
    - 计价参数（duration_seconds/resolution）写入 params_hash 绑定到 quote_token，
      防止客户端在确认扣费时篡改影响价格的入参。
    """
    using_default_model = model_id is None

    if not using_default_model:
        # 显式模型：手动按 id 取并做归属校验（resolver 不校验归属）。
        model = await db.get(Model, model_id)
        if model is None:
            # 模型不存在：交由通用 404 处理（resolver 风格一致）。
            from fastapi import HTTPException, status
            from app.services.common import entity_not_found

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Model")
            ) from None
        if model.user_id != user_id:
            raise build_model_not_owned_error(model_id=model_id, user_id=user_id)
        if model.category != category:
            raise PointsDomainError(
                code="MODEL_CATEGORY_MISMATCH",
                message=f"model {model_id} category={model.category} != requested={category}",
                status_code=400,
                data={"model_id": model_id, "model_category": str(model.category), "requested_category": str(category)},
            )
    else:
        # 默认模型解析：无默认配置会抛 503（配置错误）。
        model = await get_default_model_by_category(db, category, user_id=user_id)

    # 计价（视频缺时长/分辨率、不支持分辨率由 pricing 抛 ValueError/UnsupportedResolutionError）。
    required_points = calculate_points(
        category=category,
        unit_points=model.unit_points,
        duration_seconds=duration_seconds,
        resolution=resolution,
        generation_count=generation_count,
    )

    # 余额/可用额度（纯读取，不加锁）。
    pts = await get_points(db, user_id=user_id)
    available = pts.balance - pts.frozen
    sufficient = available >= required_points

    # 绑定影响价格的参数到 quote_token，防篡改。
    params_hash = hash_quote_params(
        {
            "category": str(category),
            "duration_seconds": duration_seconds,
            "resolution": resolution,
            "generation_count": generation_count,
        }
    )
    quote_token = create_quote_token(
        QuoteClaims(
            user_id=user_id,
            business_type=business_type,
            model_id=model.id,
            params_hash=params_hash,
            required_points=required_points,
        )
    )

    return PointsQuoteResponse(
        resolved_model_id=model.id,
        resolved_model_name=model.name,
        using_default_model=using_default_model,
        required_points=required_points,
        available_points=available,
        sufficient=sufficient,
        quote_token=quote_token,
    )


def to_summary(balance: int, frozen: int) -> PointsSummaryRead:
    """由 balance/frozen 构造账户摘要 DTO（available = balance - frozen）。"""
    return PointsSummaryRead(balance=balance, frozen=frozen, available=balance - frozen)


async def list_user_transactions(
    db: AsyncSession,
    *,
    user_id: str,
    tx_type: str | None = None,
    business_type: str | None = None,
    billing_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PointTransaction], int]:
    """分页查询某用户积分流水，按 created_at 倒序。

    过滤项：type（流水类型枚举值字符串）、business_type、billing_id。
    返回 (items, total)。
    """
    stmt = select(PointTransaction).where(PointTransaction.user_id == user_id)
    count_stmt = select(func.count()).select_from(PointTransaction).where(PointTransaction.user_id == user_id)

    if tx_type is not None:
        # 严格校验 type 值必须是合法的流水类型枚举值。非法值直接抛 ValueError，
        # 由上层路由转化为 422，避免静默退化成「永远查不到结果」的误导性空列表。
        type_filter = PointTransactionType(tx_type)
        stmt = stmt.where(PointTransaction.type == type_filter)
        count_stmt = count_stmt.where(PointTransaction.type == type_filter)
    if business_type is not None:
        stmt = stmt.where(PointTransaction.business_type == business_type)
        count_stmt = count_stmt.where(PointTransaction.business_type == business_type)
    if billing_id is not None:
        stmt = stmt.where(PointTransaction.billing_id == billing_id)
        count_stmt = count_stmt.where(PointTransaction.billing_id == billing_id)

    total = int((await db.scalar(count_stmt)) or 0)
    stmt = (
        stmt.order_by(PointTransaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await db.execute(stmt)).scalars().all())
    return items, total
