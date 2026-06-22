"""提示词模板（PromptTemplate）CRUD 业务逻辑。

为什么存在：
- 原先提示词模板 CRUD 直接写在路由层，无法承载"数据隔离"所需的 user_id 过滤。
- 本模块将 list/create/get/update/delete 下沉为 service，统一在查询里完成隔离。

隔离规则（与项目/资产不同，需放行系统模板）：
- 查询条件为 `(user_id == 当前用户) OR (is_system == True)`：用户能看到"自己的模板 +
  所有系统预置模板"，但看不到别人的模板。
- create：写入 `user_id=当前用户`、`is_system=False`（客户端不可设置 is_system）。
- update/delete：先取记录，若 `is_system` 为真 → 维持既有"禁止删改系统模板"逻辑；
  否则校验归属（user_id == 当前用户），不符按"未找到"处理。
- 路由层只透传 `current_user.id`，不承载任何隔离逻辑。
"""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.models.studio import PromptCategory, PromptTemplate
from app.schemas.studio.prompts import PromptTemplateCreate, PromptTemplateUpdate
from app.services.common import entity_not_found

PROMPT_ORDER_FIELDS = {"name", "category", "created_at", "updated_at"}


def _visible_scope(user_id: str) -> object:
    """构建"自己的模板 + 系统模板"的可见性过滤条件。

    为什么存在：list/get/update/delete 都需要同一套放行系统模板的隔离条件，
    集中在此避免各处重复且漏掉系统模板放行。
    """
    return or_(PromptTemplate.user_id == user_id, PromptTemplate.is_system.is_(True))


async def _clear_category_default(
    db: AsyncSession,
    *,
    user_id: str,
    category: PromptCategory,
    exclude_id: str | None = None,
) -> None:
    """将当前用户在同 category 下所有模板的 is_default 置为 False（排除 exclude_id）。

    仅作用于当前用户自己的模板：默认模板的"同类别唯一"约束是按用户维度维护的，
    不应触及其他用户或系统模板。
    """
    stmt = (
        update(PromptTemplate)
        .where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.category == category,
            PromptTemplate.is_default.is_(True),
        )
    )
    if exclude_id:
        stmt = stmt.where(PromptTemplate.id != exclude_id)
    await db.execute(stmt)


async def list_prompt_templates(
    db: AsyncSession,
    *,
    user_id: str,
    category: PromptCategory | None = None,
    q: str | None = None,
    is_default: bool | None = None,
    is_system: bool | None = None,
    order: str | None = None,
    is_desc: bool = False,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[PromptTemplate], int]:
    """分页查询当前用户可见的提示词模板（自己的 + 系统的）。"""
    stmt: Select = select(PromptTemplate).where(_visible_scope(user_id))
    if category is not None:
        stmt = stmt.where(PromptTemplate.category == category)
    if is_default is not None:
        stmt = stmt.where(PromptTemplate.is_default.is_(is_default))
    if is_system is not None:
        stmt = stmt.where(PromptTemplate.is_system.is_(is_system))
    stmt = apply_keyword_filter(stmt, q=q, fields=[PromptTemplate.name])
    stmt = apply_order(
        stmt,
        model=PromptTemplate,
        order=order,
        is_desc=is_desc,
        allow_fields=PROMPT_ORDER_FIELDS,
        default="created_at",
    )
    return await paginate(db, stmt=stmt, page=page, page_size=page_size)


async def get_prompt_template(db: AsyncSession, template_id: str, *, user_id: str) -> PromptTemplate:
    """获取单个模板（仅限自己的或系统的），否则按"未找到"处理。"""
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            _visible_scope(user_id),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("PromptTemplate"))
    return obj


async def create_prompt_template(
    db: AsyncSession,
    body: PromptTemplateCreate,
    *,
    user_id: str,
) -> PromptTemplate:
    """创建归属当前用户的模板（is_system 固定为 False）。"""
    # 若设为默认，先清除当前用户同类别其他默认
    if body.is_default:
        await _clear_category_default(db, user_id=user_id, category=body.category)

    obj = PromptTemplate(
        id=str(uuid.uuid4()),
        user_id=user_id,
        category=body.category,
        name=body.name,
        content=body.content,
        preview=body.preview,
        variables=body.variables,
        is_default=body.is_default,
        is_system=False,  # 客户端不可设置
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


async def update_prompt_template(
    db: AsyncSession,
    template_id: str,
    body: PromptTemplateUpdate,
    *,
    user_id: str,
) -> PromptTemplate:
    """局部更新模板。系统模板禁止修改；他人模板按"未找到"处理。"""
    obj = await get_prompt_template(db, template_id, user_id=user_id)
    if obj.is_system:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="系统预置提示词不可修改")

    # 若将当前记录设为默认，先清除当前用户同类别其他默认
    if body.is_default is True:
        await _clear_category_default(
            db,
            user_id=user_id,
            category=cast(PromptCategory, cast(object, obj.category)),
            exclude_id=template_id,
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(obj, field, value)

    await db.flush()
    await db.refresh(obj)
    return obj


async def delete_prompt_template(db: AsyncSession, template_id: str, *, user_id: str) -> None:
    """删除模板。系统模板禁止删除；默认模板禁止删除；他人模板按"未找到"处理。"""
    obj = await get_prompt_template(db, template_id, user_id=user_id)
    if obj.is_system:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="系统预置提示词不可删除")
    if obj.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="默认提示词不可删除，请先将其他提示词设为默认",
        )
    await db.delete(obj)
