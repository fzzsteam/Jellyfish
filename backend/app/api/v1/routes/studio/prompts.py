"""提示词模板相关路由：CRUD。

路由层职责：收参 + 鉴权（注入 current_user）+ 调 service + 返回 ApiResponse。
数据隔离与业务规则（系统模板放行/禁止删改、默认唯一等）全部在 service 层，
路由仅透传 `current_user.id`。

业务规则（实现见 service）：
- is_system=True 的记录禁止修改和删除（403）。
- is_default=True 的记录禁止删除（403）。
- 同一 category 下至多一条 is_default=True（按用户维度）：创建/更新时将同 category 其余记录置为 False。
- id 由后端自动生成 UUID；is_system 不接受客户端传入（固定为 False）。
- 列表/详情按"自己的模板 + 系统模板"过滤，看不到别人的模板。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.studio import PromptCategory
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedData, created_response, empty_response, paginated_response, success_response
from app.schemas.studio.prompts import (
    PromptCategoryOptionRead,
    PromptTemplateCreate,
    PromptTemplateRead,
    PromptTemplateUpdate,
)
from app.services.studio import prompts as prompt_service

router = APIRouter()

_PROMPT_CATEGORY_ZH: dict[PromptCategory, tuple[str, str]] = {
    # 用于提交给图片模型的提示词
    PromptCategory.frame_head_image: ("首帧图片", "用于生成首帧图片的提示词"),
    PromptCategory.frame_tail_image: ("尾帧图片", "用于生成尾帧图片的提示词"),
    PromptCategory.frame_key_image: ("关键帧图片", "用于生成关键帧图片的提示词"),
    PromptCategory.character_image_front: ("角色正面图片", "用于生成角色正面图片的提示词"),
    PromptCategory.character_image_other: ("角色侧面/背面图片", "用于生成角色侧面或背面图片的提示词"),
    PromptCategory.actor_image_front: ("演员正面图片", "用于生成演员正面图片的提示词"),
    PromptCategory.actor_image_other: ("演员侧面/背面图片", "用于生成演员侧面或背面图片的提示词"),
    PromptCategory.prop_image_front: ("道具正面图片", "用于生成道具正面图片的提示词"),
    PromptCategory.prop_image_other: ("道具侧面/背面图片", "用于生成道具侧面或背面图片的提示词"),
    PromptCategory.scene_image_front: ("场景正面图片", "用于生成场景正面图片的提示词"),
    PromptCategory.scene_image_other: ("场景侧面/背面图片", "用于生成场景侧面或背面图片的提示词"),
    PromptCategory.costume_image_front: ("服装正面图片", "用于生成服装正面图片的提示词"),
    PromptCategory.costume_image_other: ("服装侧面/背面图片", "用于生成服装侧面或背面图片的提示词"),
    # 用于提交给文本模型的提示词
    PromptCategory.frame_head_prompt: ("首帧图片提示词", "用于生成首帧图片文案的提示词"),
    PromptCategory.frame_tail_prompt: ("尾帧图片提示词", "用于生成尾帧图片文案的提示词"),
    PromptCategory.frame_key_prompt: ("关键帧图片提示词", "用于生成关键帧图片文案的提示词"),
    PromptCategory.video_prompt: ("视频提示词", "用于视频生成的整体提示词"),
    PromptCategory.storyboard_prompt: ("分镜提示词", "用于分镜拆解与描述的提示词"),
    # 预留/扩展类别（即使暂时不用，也需要完整映射用于前端展示与校验）
    PromptCategory.combined: ("组合提示词", "用于组合多段提示词的模板"),
    PromptCategory.bgm: ("背景音乐提示词", "用于生成背景音乐描述的提示词"),
    PromptCategory.sfx: ("音效提示词", "用于生成音效描述的提示词"),
}


# ---------- 列表 ----------

@router.get(
    "",
    response_model=ApiResponse[PaginatedData[PromptTemplateRead]],
    summary="提示词模板列表（分页）",
)
async def list_prompt_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    category: PromptCategory | None = Query(None, description="按类别过滤"),
    q: str | None = Query(None, description="关键字，过滤 name"),
    is_default: bool | None = Query(None, description="过滤是否为默认"),
    is_system: bool | None = Query(None, description="过滤是否为系统预置"),
    order: str | None = Query(None),
    is_desc: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[PromptTemplateRead]]:
    items, total = await prompt_service.list_prompt_templates(
        db,
        user_id=current_user.id,
        category=category,
        q=q,
        is_default=is_default,
        is_system=is_system,
        order=order,
        is_desc=is_desc,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        [PromptTemplateRead.model_validate(x) for x in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/categories",
    response_model=ApiResponse[list[PromptCategoryOptionRead]],
    summary="获取提示词类别枚举（含中文映射）",
)
async def list_prompt_categories() -> ApiResponse[list[PromptCategoryOptionRead]]:
    items: list[PromptCategoryOptionRead] = []
    for category in PromptCategory:
        label, description = _PROMPT_CATEGORY_ZH.get(category, (category.value, ""))
        items.append(PromptCategoryOptionRead(value=category, label=label, description=description))
    return success_response(items)


# ---------- 详情 ----------

@router.get(
    "/{template_id}",
    response_model=ApiResponse[PromptTemplateRead],
    summary="获取提示词模板详情",
)
async def get_prompt_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[PromptTemplateRead]:
    obj = await prompt_service.get_prompt_template(db, template_id, user_id=current_user.id)
    return success_response(PromptTemplateRead.model_validate(obj))


# ---------- 创建 ----------

@router.post(
    "",
    response_model=ApiResponse[PromptTemplateRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建提示词模板",
)
async def create_prompt_template(
    body: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[PromptTemplateRead]:
    obj = await prompt_service.create_prompt_template(db, body, user_id=current_user.id)
    return created_response(PromptTemplateRead.model_validate(obj))


# ---------- 更新 ----------

@router.patch(
    "/{template_id}",
    response_model=ApiResponse[PromptTemplateRead],
    summary="局部更新提示词模板",
)
async def update_prompt_template(
    template_id: str,
    body: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[PromptTemplateRead]:
    obj = await prompt_service.update_prompt_template(db, template_id, body, user_id=current_user.id)
    return success_response(PromptTemplateRead.model_validate(obj))


# ---------- 删除 ----------

@router.delete(
    "/{template_id}",
    response_model=ApiResponse[None],
    summary="删除提示词模板",
)
async def delete_prompt_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[None]:
    await prompt_service.delete_prompt_template(db, template_id, user_id=current_user.id)
    return empty_response()
