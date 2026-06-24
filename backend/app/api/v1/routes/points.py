"""积分用户端点：余额摘要、流水查询、试算。

挂载时统一注入 `get_current_user`（见 app/api/v1/__init__.py），故此处只声明 db/user 依赖。
保持路由层瘦身：收参 → 调 service → 返回 ApiResponse。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.points import PointTransaction
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedData, paginated_response, success_response
from app.schemas.points import (
    PointTransactionRead,
    PointsQuoteRequest,
    PointsQuoteResponse,
    PointsSummaryRead,
    GroupedTransactionResponse,
    OperationGroupRead,
)
from app.services.points import UnsupportedResolutionError
from app.services.points.billing import list_user_transactions, quote_points, to_summary
from app.services.points.ledger import get_points


_SYSTEM_CREATED_BY = "system"
_SYSTEM_CREATED_BY_DISPLAY = "系统自动"


async def _resolve_usernames(db: AsyncSession, items: list[PointTransaction]) -> dict[str, str]:
    """从流水列表中取出 created_by ID 集合，批量查一次 users 表，返回 id→username 映射。
    "system" 为系统自动触发的保留值，不走 DB 查询，直接映射为"系统自动"。
    """
    ids = {tx.created_by for tx in items if tx.created_by and tx.created_by != _SYSTEM_CREATED_BY}
    result: dict[str, str] = {_SYSTEM_CREATED_BY: _SYSTEM_CREATED_BY_DISPLAY}
    if not ids:
        return result
    rows = await db.execute(select(User.id, User.username).where(User.id.in_(ids)))
    result.update({row.id: row.username for row in rows})
    return result

router = APIRouter()


@router.get("/me", response_model=ApiResponse[PointsSummaryRead], summary="当前用户积分摘要")
async def get_my_points(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PointsSummaryRead]:
    """返回当前用户余额/冻结/可用额度（纯读取，首次访问自动初始化为 0）。"""
    pts = await get_points(db, user_id=current_user.id)
    return success_response(to_summary(balance=pts.balance, frozen=pts.frozen))


@router.get(
    "/transactions",
    response_model=ApiResponse[PaginatedData[PointTransactionRead]],
    summary="当前用户积分流水",
)
async def list_my_transactions(
    type: str | None = Query(None, description="按流水类型过滤：recharge/freeze/consume/unfreeze"),
    business_type: str | None = Query(None, description="按业务类型过滤"),
    billing_id: str | None = Query(None, description="按计费单据 ID 过滤"),
    id: str | None = Query(None, description="按流水 ID 精确搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PaginatedData[PointTransactionRead]]:
    """分页查询当前用户积分流水，按 created_at 倒序。

    非法 `type`（非 recharge/freeze/consume/unfreeze）→ 422。
    """
    try:
        items, total = await list_user_transactions(
            db,
            user_id=current_user.id,
            tx_type=type,
            business_type=business_type,
            billing_id=billing_id,
            transaction_id=id,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    user_map = await _resolve_usernames(db, items)
    return paginated_response(
        [
            PointTransactionRead.model_validate(tx).model_copy(
                update={"created_by_username": user_map.get(tx.created_by) if tx.created_by else None}
            )
            for tx in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/transactions/grouped",
    response_model=ApiResponse[GroupedTransactionResponse],
    summary="按操作组聚合的积分流水",
)
async def list_grouped_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    cascade_group_id: str | None = Query(None, description="按操作ID精确搜索"),
    billing_id: str | None = Query(None, description="按账单ID搜索，返回所属操作组"),
    transaction_id: str | None = Query(None, description="按流水ID搜索，返回所属操作组"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[GroupedTransactionResponse]:
    """按 cascade_group_id 聚合展示流水。同一操作级联的多个 billing_id 归为一组。

    支持三种 ID 搜索：
    - cascade_group_id：直接按操作组 ID 过滤
    - billing_id：先解析到所属操作组，再返回该组数据
    - transaction_id：先解析到所属操作组，再返回该组数据，并在 matched_transaction_id 中标记命中流水 ID
    """
    from app.services.points.billing import list_grouped_transactions as _list_grouped

    groups, total, matched_transaction_id, simple_txns = await _list_grouped(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        cascade_group_id=cascade_group_id,
        billing_id=billing_id,
        transaction_id=transaction_id,
    )

    # 解析 billing 层的 created_by → username
    created_by_ids = {
        b["created_by"]
        for g in groups for b in g.get("billings", [])
        if b.get("created_by") and b["created_by"] != _SYSTEM_CREATED_BY
    }
    user_map: dict[str, str] = {_SYSTEM_CREATED_BY: _SYSTEM_CREATED_BY_DISPLAY}
    # 补充简单流水的 created_by
    for tx in simple_txns:
        if tx.created_by and tx.created_by not in user_map:
            created_by_ids.add(tx.created_by)
    if created_by_ids:
        rows = await db.execute(select(User.id, User.username).where(User.id.in_(created_by_ids)))
        user_map.update({r.id: r.username for r in rows})
    for g in groups:
        for b in g.get("billings", []):
            b["created_by_username"] = user_map.get(b.get("created_by") or "", None)

    # 解析简单流水的 created_by → username
    simple_txns_models = []
    for tx in simple_txns:
        read = PointTransactionRead.model_validate(tx)
        read.created_by_username = user_map.get(tx.created_by) if tx.created_by else None
        simple_txns_models.append(read)

    from app.schemas.common import Pagination

    max_page = max(1, (total + page_size - 1) // page_size) if page_size > 0 else 1
    pagination = Pagination(
        page=page,
        page_size=page_size,
        total=total,
        max_page=max_page,
    )
    return success_response(
        GroupedTransactionResponse(
            items=[OperationGroupRead(**g) for g in groups],
            pagination=pagination,
            matched_transaction_id=matched_transaction_id,
            simple_txns=simple_txns_models,
        )
    )


@router.post("/quote", response_model=ApiResponse[PointsQuoteResponse], summary="积分试算")
async def quote_my_points(
    body: PointsQuoteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PointsQuoteResponse]:
    """试算本次生成所需积分并签发短期 quote_token。

    - 不支持的视频分辨率 → 400。
    - 显式 model_id 归属他人 → PointsDomainError(403) 由 main.py 处理器序列化。
    - 用户未配置默认模型 → 503（配置错误，由通用处理器兜底）。
    """
    try:
        resp = await quote_points(
            db,
            user_id=current_user.id,
            business_type=body.business_type,
            category=body.category,
            model_id=body.model_id,
            duration_seconds=body.duration_seconds,
            resolution=body.resolution,
            resolution_profile=body.resolution_profile,
            generation_count=body.generation_count,
        )
    except UnsupportedResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return success_response(resp)
