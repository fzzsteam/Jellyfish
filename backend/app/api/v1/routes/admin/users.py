"""管理员用户管理端点：创建、列表、详情、修改、查看某用户项目。

挂载时整体注入 `require_admin`（见 app/api/v1/__init__.py），故此处不重复鉴权。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.auth import UserAdminRead, UserCreate, UserUpdate
from app.schemas.common import ApiResponse, created_response, paginated_response, success_response
from app.services import admin as admin_service
from app.services.common import entity_already_exists, entity_not_found
from app.services.studio import projects as project_service

router = APIRouter()


@router.get("", response_model=ApiResponse, summary="用户列表")
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
async def update_user(user_id: str, body: UserUpdate, db: AsyncSession = Depends(get_db)):
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


@router.get("/{user_id}/projects", response_model=ApiResponse, summary="查看某用户的项目")
async def list_user_projects(user_id: str, db: AsyncSession = Depends(get_db)):
    # 管理员以目标 user_id 走与普通用户同一套隔离 service，不开特权查询路径。
    # list_projects 返回 (items, total) 元组，这里只取项目列表。
    projects, _total = await project_service.list_projects(db, user_id=user_id)
    return success_response([{"id": p.id, "name": p.name} for p in projects])
