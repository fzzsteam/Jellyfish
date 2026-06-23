"""管理员用户管理端点：创建、列表、详情、修改、查看某用户项目。

挂载时整体注入 `require_admin`（见 app/api/v1/__init__.py），故此处不重复鉴权。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import User
from app.schemas.auth import (
    ResetPasswordRead,
    UserAdminRead,
    UserCreate,
    UserProjectBrief,
    UserUpdate,
)
from app.schemas.common import (
    ApiResponse,
    PaginatedData,
    created_response,
    paginated_response,
    success_response,
)
from app.schemas.points import PointTransactionRead, PointsRechargeRequest, PointsSummaryRead
from app.services import admin as admin_service
from app.services.common import entity_already_exists, entity_not_found
from app.services.points import ledger as points_ledger
from app.services.points.billing import (
    PointsDomainError,
    build_insufficient_error,
    list_user_transactions,
    to_summary,
)
from app.services.studio import projects as project_service

router = APIRouter()


_SYSTEM_CREATED_BY = "system"
_SYSTEM_CREATED_BY_DISPLAY = "系统自动"


async def _resolve_usernames(db: AsyncSession, items: list) -> dict[str, str]:
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


@router.get("", response_model=ApiResponse[PaginatedData[UserAdminRead]], summary="用户列表")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await admin_service.list_users(db, page=page, page_size=page_size)
    return paginated_response(
        [UserAdminRead.model_validate(u) for u in items], total=total, page=page, page_size=page_size
    )


@router.post("", response_model=ApiResponse[UserAdminRead], status_code=status.HTTP_201_CREATED, summary="创建用户")
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        user = await admin_service.create_user(
            db, username=body.username, password=body.password, is_admin=body.is_admin
        )
    except admin_service.UsernameExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=entity_already_exists("User")) from exc
    return created_response(UserAdminRead.model_validate(user))


@router.get("/{user_id}", response_model=ApiResponse[UserAdminRead], summary="用户详情")
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    try:
        user = await admin_service.get_user(db, user_id)
    except admin_service.UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("User")) from exc
    return success_response(UserAdminRead.model_validate(user))


@router.patch("/{user_id}", response_model=ApiResponse[UserAdminRead], summary="修改用户")
async def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # 管理员不能修改自己的启用/禁用状态（与重置密码同样禁止操作自己）
    if user_id == current_user.id and body.is_active is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot change your own active status",
        )
    try:
        user = await admin_service.update_user(
            db, user_id, password=body.password, is_active=body.is_active, is_admin=body.is_admin
        )
    except admin_service.UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("User")) from exc
    except admin_service.LastAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="cannot disable or demote the last active admin"
        ) from exc
    return success_response(UserAdminRead.model_validate(user))


@router.post(
    "/{user_id}/reset-password",
    response_model=ApiResponse[ResetPasswordRead],
    summary="重置用户密码",
)
async def reset_password(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ResetPasswordRead]:
    """管理员重置目标用户密码；后端生成一次性临时密码并返回。

    不允许重置自己（应通过自助改密接口）；目标用户不存在返回 404。
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot reset your own password, use change-password instead",
        )
    try:
        user, temporary_password = await admin_service.reset_password(db, user_id)
    except admin_service.UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("User")
        ) from exc
    return success_response(
        ResetPasswordRead(
            user=UserAdminRead.model_validate(user),
            temporary_password=temporary_password,
        )
    )


@router.get(
    "/{user_id}/projects",
    response_model=ApiResponse[list[UserProjectBrief]],
    summary="查看某用户的项目",
)
async def list_user_projects(user_id: str, db: AsyncSession = Depends(get_db)):
    # 管理员以目标 user_id 走与普通用户同一套隔离 service，不开特权查询路径。
    # list_projects 返回 (items, total) 元组，这里只取项目列表。
    projects, _total = await project_service.list_projects(db, user_id=user_id)
    return success_response([UserProjectBrief.model_validate(p) for p in projects])


# ---------------------------------------------------------------------------
# 积分管理端点（挂载在 admin 路由下，整体 admin 鉴权）
# ---------------------------------------------------------------------------


@router.get(
    "/{user_id}/points",
    response_model=ApiResponse[PointsSummaryRead],
    summary="查看某用户积分摘要",
)
async def get_user_points(user_id: str, db: AsyncSession = Depends(get_db)):
    """返回目标用户余额/冻结/可用额度。"""
    pts = await points_ledger.get_points(db, user_id=user_id)
    return success_response(to_summary(balance=pts.balance, frozen=pts.frozen))


@router.get(
    "/{user_id}/points/transactions",
    response_model=ApiResponse[PaginatedData[PointTransactionRead]],
    summary="查看某用户积分流水",
)
async def list_user_points_transactions(
    user_id: str,
    type: str | None = Query(None, description="流水类型"),
    business_type: str | None = Query(None, description="业务类型"),
    billing_id: str | None = Query(None, description="计费单据 ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """分页查询目标用户积分流水，按 created_at 倒序。

    非法 `type`（非 recharge/freeze/consume/unfreeze）→ 422。
    """
    try:
        items, total = await list_user_transactions(
            db,
            user_id=user_id,
            tx_type=type,
            business_type=business_type,
            billing_id=billing_id,
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


@router.post(
    "/{user_id}/points/recharge",
    response_model=ApiResponse[PointTransactionRead],
    summary="管理员充值/扣减用户积分",
)
async def recharge_user_points(
    user_id: str,
    body: PointsRechargeRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """对目标用户积分账户充值（正）或扣减（负）。

    - 负充值必须带 remark（否则 ledger 抛 ValueError → 400）。
    - 负充值不得侵蚀冻结额（否则抛 InsufficientPointsError → PointsDomainError 402）。
    """
    try:
        tx = await points_ledger.recharge(
            db,
            user_id=user_id,
            amount=body.amount,
            created_by=current_user.id,
            remark=body.remark,
        )
    except points_ledger.InsufficientPointsError as exc:
        # 侵蚀冻结/余额不足：转结构化领域错误（HTTP 402）。
        raise build_insufficient_error(
            available=exc.available, required=exc.required, shortfall=exc.shortfall
        ) from exc
    except ValueError as exc:
        # amount=0 / 负充值无备注等参数错误 → 400。
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    read = PointTransactionRead.model_validate(tx).model_copy(
        update={"created_by_username": current_user.username}
    )
    return success_response(read)
