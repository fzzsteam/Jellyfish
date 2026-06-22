"""项目（Project）CRUD 业务逻辑。

为什么存在：
- 原先项目 CRUD 直接写在路由层，无法承载"数据隔离"所需的 user_id 过滤。
- 本模块将项目的 list/create/get/update/delete 下沉为 service，统一在查询的
  `where(Project.user_id == user_id)` 与单条归属校验里完成隔离；路由层只透传
  `current_user.id`，不承载任何隔离逻辑。
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.models.studio import FileUsage, Project
from app.models.types import ProjectStyle, ProjectVisualStyle
from app.schemas.studio.projects import ProjectCreate, ProjectUpdate
from app.services.common import (
    create_and_refresh,
    entity_already_exists,
    entity_not_found,
    ensure_not_exists,
    flush_and_refresh,
    patch_model,
)

PROJECT_ORDER_FIELDS = {"name", "created_at", "updated_at", "progress"}


def build_project_style_options() -> tuple[dict[ProjectVisualStyle, list[ProjectStyle]], dict[ProjectVisualStyle, ProjectStyle]]:
    """构建"视觉风格 -> 可选题材风格"映射及各视觉风格的默认题材。

    纯枚举派生逻辑，与用户无关，故不参与 user_id 隔离。
    """
    mapping: dict[ProjectVisualStyle, list[ProjectStyle]] = {key: [] for key in ProjectVisualStyle}
    for item in ProjectStyle:
        if item.name.startswith("real_people_"):
            mapping[ProjectVisualStyle.live_action].append(item)
            continue
        if item.name.startswith("anime_") or item.name in {"guoman", "ink_wash"}:
            mapping[ProjectVisualStyle.anime].append(item)
            continue
    defaults: dict[ProjectVisualStyle, ProjectStyle] = {
        visual: styles[0]
        for visual, styles in mapping.items()
        if styles
    }
    return mapping, defaults


def _validate_project_style_combo(*, visual_style: ProjectVisualStyle, style: ProjectStyle) -> None:
    """校验题材风格是否属于所选视觉风格，不匹配抛出 400。"""
    mapping, _defaults = build_project_style_options()
    allowed = mapping.get(visual_style, [])
    if style not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"style is not allowed for visual_style: visual_style={visual_style.value}, "
                f"style={style.value}, allowed={[item.value for item in allowed]}"
            ),
        )


async def list_projects(
    db: AsyncSession,
    *,
    user_id: str,
    q: str | None = None,
    order: str | None = None,
    is_desc: bool = False,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[Project], int]:
    """分页列出当前用户拥有的项目（按 user_id 隔离）。"""
    stmt = select(Project).where(Project.user_id == user_id)
    stmt = apply_keyword_filter(stmt, q=q, fields=[Project.name, Project.description])
    stmt = apply_order(
        stmt,
        model=Project,
        order=order,
        is_desc=is_desc,
        allow_fields=PROJECT_ORDER_FIELDS,
        default="created_at",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return items, total


async def get_project(db: AsyncSession, project_id: str, *, user_id: str) -> Project:
    """获取归属当前用户的项目；不存在或不归属时按"未找到"处理（404）。"""
    obj = await db.get(Project, project_id)
    if obj is None or obj.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=entity_not_found("Project"),
        )
    return obj


async def create_project(db: AsyncSession, body: ProjectCreate, *, user_id: str) -> Project:
    """创建项目并写入归属 user_id。"""
    await ensure_not_exists(
        db,
        Project,
        body.id,
        detail=entity_already_exists("Project"),
    )
    _validate_project_style_combo(visual_style=body.visual_style, style=body.style)
    obj = await create_and_refresh(db, Project(**body.model_dump(), user_id=user_id))
    return obj


async def update_project(
    db: AsyncSession,
    project_id: str,
    body: ProjectUpdate,
    *,
    user_id: str,
) -> Project:
    """更新归属当前用户的项目；非归属按"未找到"处理（404）。"""
    obj = await get_project(db, project_id, user_id=user_id)
    update_data = body.model_dump(exclude_unset=True)
    visual_style = update_data.get("visual_style", obj.visual_style)
    style = update_data.get("style", obj.style)
    if visual_style is not None and style is not None:
        _validate_project_style_combo(visual_style=visual_style, style=style)
    patch_model(obj, update_data)
    await flush_and_refresh(db, obj)
    return obj


async def delete_project(db: AsyncSession, project_id: str, *, user_id: str) -> None:
    """删除归属当前用户的项目；非归属按"未找到"处理（404）。

    删除前先清理关联 file_usages，避免外键约束失败：
    - 删除该项目自身关联的 file_usages；
    - 清理所有 orphan file_usages（project_id 不指向任何存在的项目）。
    """
    obj = await db.get(Project, project_id)
    if obj is None or obj.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=entity_not_found("Project"),
        )

    # 1. 删除该 project 关联的 file_usages
    await db.execute(
        sql_delete(FileUsage).where(FileUsage.project_id == project_id)
    )

    # 2. 清理所有 orphan file_usages（project_id 不对应任何存在的 project）
    await db.execute(
        sql_delete(FileUsage).where(
            FileUsage.project_id.notin_(
                select(Project.id).scalar_subquery()
            )
        )
    )

    # 3. 再删除 project 本身
    await db.delete(obj)
    await db.flush()
