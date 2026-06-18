"""Project CRUD。

路由层职责：收参 + 鉴权（注入 current_user）+ 调 service + 返回 ApiResponse。
数据隔离逻辑全部在 service 层，路由仅透传 `current_user.id`。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedData, created_response, empty_response, paginated_response, success_response
from app.schemas.studio.projects import (
    ProjectCreate,
    ProjectRead,
    ProjectStyleOptionsRead,
    ProjectUpdate,
    StyleOption,
)
from app.services.studio import projects as project_service
from app.models.types import ProjectStyle, ProjectVisualStyle

router = APIRouter()


@router.get(
    "/style-options",
    response_model=ApiResponse[ProjectStyleOptionsRead],
    summary="获取项目风格候选项",
)
async def get_project_style_options(
) -> ApiResponse[ProjectStyleOptionsRead]:
    mapping, defaults = project_service.build_project_style_options()
    data = ProjectStyleOptionsRead(
        visual_styles=[StyleOption(value=x.value, label=x.value) for x in ProjectVisualStyle],
        styles_by_visual_style={
            visual.value: [StyleOption(value=style.value, label=style.value) for style in styles]
            for visual, styles in mapping.items()
        },
        default_style_by_visual_style={visual.value: style.value for visual, style in defaults.items()},
    )
    return success_response(data)


@router.get(
    "",
    response_model=ApiResponse[PaginatedData[ProjectRead]],
    summary="项目列表（分页）",
)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    q: str | None = Query(None, description="关键字，过滤 name/description"),
    order: str | None = Query(None, description="排序字段"),
    is_desc: bool = Query(False, description="是否倒序"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[ProjectRead]]:
    items, total = await project_service.list_projects(
        db,
        user_id=current_user.id,
        q=q,
        order=order,
        is_desc=is_desc,
        page=page,
        page_size=page_size,
    )
    return paginated_response([ProjectRead.model_validate(x) for x in items], page=page, page_size=page_size, total=total)


@router.post(
    "",
    response_model=ApiResponse[ProjectRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建项目",
)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ProjectRead]:
    obj = await project_service.create_project(db, body, user_id=current_user.id)
    return created_response(ProjectRead.model_validate(obj))


@router.get(
    "/{project_id}",
    response_model=ApiResponse[ProjectRead],
    summary="获取项目",
)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ProjectRead]:
    obj = await project_service.get_project(db, project_id, user_id=current_user.id)
    return success_response(ProjectRead.model_validate(obj))


@router.patch(
    "/{project_id}",
    response_model=ApiResponse[ProjectRead],
    summary="更新项目",
)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ProjectRead]:
    obj = await project_service.update_project(db, project_id, body, user_id=current_user.id)
    return success_response(ProjectRead.model_validate(obj))


@router.delete(
    "/{project_id}",
    response_model=ApiResponse[None],
    summary="删除项目",
)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[None]:
    await project_service.delete_project(db, project_id, user_id=current_user.id)
    return empty_response()
