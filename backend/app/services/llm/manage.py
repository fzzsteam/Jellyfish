"""LLM 管理服务：Provider / Model / ModelSettings 的查询与 CRUD。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.core.integrations.image_capabilities import (
    DEFAULT_VIDEO_REFERENCE_RATIO_SIZE_MAP,
    resolve_image_capability,
)
from app.core.integrations.video_capabilities import resolve_default_ratio, resolve_video_capability
from app.schemas.common import ApiResponse, PaginatedData, paginated_response
from app.schemas.llm import (
    ImageGenerationOptionsRead,
    ModelCreate,
    ModelRead,
    ModelSettingsUpdate,
    ModelUpdate,
    ProviderCreate,
    ProviderRead,
    ProviderSupportedRead,
    VideoGenerationOptionsRead,
    ProviderUpdate,
)
from app.services.llm.provider_registry import (
    is_provider_category_supported,
    list_registered_providers,
    resolve_provider_key_from_name,
)
from app.bootstrap import bootstrap_all_registries
from app.services.common import (
    create_and_refresh,
    entity_already_exists,
    entity_not_found,
    ensure_not_exists,
    flush_and_refresh,
    get_or_404,
    patch_model,
)


async def list_providers_paginated(
    db: AsyncSession,
    *,
    q: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
    allow_fields: set[str],
) -> ApiResponse[PaginatedData[ProviderRead]]:
    """分页查询全局供应商列表（无用户隔离）。"""
    stmt = select(Provider)
    stmt = apply_keyword_filter(stmt, q=q, fields=[Provider.name, Provider.description])
    stmt = apply_order(
        stmt,
        model=Provider,
        order=order,
        is_desc=is_desc,
        allow_fields=allow_fields,
        default="created_at",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response(
        [ProviderRead.model_validate(x) for x in items],
        page=page,
        page_size=page_size,
        total=total,
    )


async def create_provider(
    db: AsyncSession,
    *,
    body: ProviderCreate,
) -> Provider:
    """创建全局供应商（仅管理员路由调用）。"""
    await ensure_not_exists(
        db,
        Provider,
        body.id,
        detail=entity_already_exists("Provider"),
        status_code=400,
    )
    return await create_and_refresh(
        db,
        Provider(
            id=body.id,
            name=body.name,
            base_url=body.base_url,
            image_base_url=body.image_base_url,
            video_base_url=body.video_base_url,
            api_key=body.api_key,
            api_secret=body.api_secret,
            description=body.description,
            status=body.status,
            created_by=body.created_by,
        ),
    )


async def _get_provider(db: AsyncSession, *, provider_id: str) -> Provider:
    """按 ID 获取供应商；不存在时 404。"""
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=entity_not_found("Provider"),
        )
    return provider


async def get_provider(
    db: AsyncSession,
    *,
    provider_id: str,
) -> Provider:
    """获取单个供应商（全局可见）。"""
    return await _get_provider(db, provider_id=provider_id)


async def update_provider(
    db: AsyncSession,
    *,
    provider_id: str,
    body: ProviderUpdate,
) -> Provider:
    """更新供应商（仅管理员路由调用）。"""
    provider = await _get_provider(db, provider_id=provider_id)
    patch_model(provider, body.model_dump(exclude_unset=True))
    return await flush_and_refresh(db, provider)


async def delete_provider(
    db: AsyncSession,
    *,
    provider_id: str,
) -> None:
    """删除供应商（仅管理员路由调用；不存在时静默忽略）。"""
    provider = await db.get(Provider, provider_id)
    if provider is None:
        return
    await db.delete(provider)
    await db.flush()


async def list_models_paginated(
    db: AsyncSession,
    *,
    provider_id: str | None,
    category: ModelCategoryKey | None,
    q: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
    allow_fields: set[str],
) -> ApiResponse[PaginatedData[ModelRead]]:
    """分页查询全局模型列表（无用户隔离）。"""
    stmt = select(Model)
    if provider_id is not None:
        stmt = stmt.where(Model.provider_id == provider_id)
    if category is not None:
        stmt = stmt.where(Model.category == category)
    stmt = apply_keyword_filter(stmt, q=q, fields=[Model.name, Model.description])
    stmt = apply_order(
        stmt,
        model=Model,
        order=order,
        is_desc=is_desc,
        allow_fields=allow_fields,
        default="created_at",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response(
        [ModelRead.model_validate(x) for x in items],
        page=page,
        page_size=page_size,
        total=total,
    )


async def _require_provider(db: AsyncSession, *, provider_id: str) -> Provider:
    """创建/更新模型时校验 provider 存在且 category 支持；不存在按 400 处理。"""
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=entity_not_found("Provider"),
        )
    return provider


async def create_model(
    db: AsyncSession,
    *,
    body: ModelCreate,
) -> Model:
    """创建全局模型（仅管理员路由调用）。"""
    await ensure_not_exists(
        db,
        Model,
        body.id,
        detail=entity_already_exists("Model"),
        status_code=400,
    )
    provider = await _require_provider(db, provider_id=body.provider_id)
    _ensure_provider_supports_category(provider=provider, category=body.category)
    return await create_and_refresh(
        db,
        Model(
            id=body.id,
            name=body.name,
            category=body.category,
            provider_id=body.provider_id,
            params=body.params,
            unit_points=body.unit_points,
            description=body.description,
            created_by=body.created_by,
        ),
    )


async def _get_model(db: AsyncSession, *, model_id: str) -> Model:
    """按 ID 获取模型；不存在时 404。"""
    model = await db.get(Model, model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=entity_not_found("Model"),
        )
    return model


async def get_model(
    db: AsyncSession,
    *,
    model_id: str,
) -> Model:
    """获取单个模型（全局可见）。"""
    return await _get_model(db, model_id=model_id)


async def update_model(
    db: AsyncSession,
    *,
    model_id: str,
    body: ModelUpdate,
) -> Model:
    """更新模型（仅管理员路由调用）。"""
    model = await _get_model(db, model_id=model_id)
    update_data = body.model_dump(exclude_unset=True)
    target_category = update_data.get("category", model.category)
    target_provider_id = update_data.get("provider_id", model.provider_id)
    target_provider = await _require_provider(db, provider_id=target_provider_id)
    _ensure_provider_supports_category(provider=target_provider, category=target_category)
    patch_model(model, update_data)
    return await flush_and_refresh(db, model)


async def delete_model(
    db: AsyncSession,
    *,
    model_id: str,
) -> None:
    """删除模型（仅管理员路由调用；不存在时静默忽略）。"""
    model = await db.get(Model, model_id)
    if model is None:
        return
    await db.delete(model)
    await db.flush()


async def get_or_create_settings(db: AsyncSession, *, user_id: str) -> ModelSettings:
    """按 user_id 获取设置行；不存在则惰性创建（每用户一行，幂等）。"""
    result = await db.execute(select(ModelSettings).where(ModelSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = ModelSettings(user_id=user_id)
        db.add(settings)
        await db.flush()
    return settings


async def get_model_settings(db: AsyncSession, *, user_id: str) -> ModelSettings:
    """读取某用户的模型设置（不存在则惰性创建默认值）。"""
    return await get_or_create_settings(db, user_id=user_id)


async def update_model_settings(
    db: AsyncSession,
    *,
    user_id: str,
    body: ModelSettingsUpdate | None = None,
    **fields: object,
) -> ModelSettings:
    """按 user_id upsert 模型设置；只更新传入的字段。

    兼容两种入参：路由层传入 `body`（`ModelSettingsUpdate` schema），
    服务/测试层可直接以关键字参数传入要更新的字段。仅写入非 None 的字段，
    保持“按 user_id 定位单行”的 upsert 语义。
    """
    settings = await get_or_create_settings(db, user_id=user_id)
    if body is not None:
        patch_model(settings, body.model_dump())
    for key, value in fields.items():
        if value is not None:
            setattr(settings, key, value)
    await db.flush()
    return settings


async def get_video_generation_options(
    db: AsyncSession,
    *,
    user_id: str,
) -> VideoGenerationOptionsRead:
    """返回当前用户默认视频模型的动态 ratio 枚举。"""
    settings = await get_or_create_settings(db, user_id=user_id)
    model_id = settings.default_video_model_id
    if not model_id:
        return VideoGenerationOptionsRead(
            provider="",
            model_id="",
            model_name="",
            allowed_ratios=["16:9"],
            default_ratio="16:9",
        )

    model = await get_or_404(db, Model, model_id, detail=entity_not_found("Model"))
    provider = await get_or_404(db, Provider, model.provider_id, detail=entity_not_found("Provider"))
    provider_key = resolve_provider_key_from_name(provider.name)
    capability = resolve_video_capability(provider=provider_key, model=model.name)
    allowed_ratios = sorted(capability.allowed_ratios or {"16:9"})
    default_ratio = resolve_default_ratio(provider=provider_key, model=model.name) or allowed_ratios[0]
    if default_ratio not in allowed_ratios:
        allowed_ratios = sorted({*allowed_ratios, default_ratio})

    return VideoGenerationOptionsRead(
        provider=provider_key,
        model_id=model.id,
        model_name=model.name,
        allowed_ratios=allowed_ratios,
        default_ratio=default_ratio,
    )


async def get_image_generation_options(
    db: AsyncSession,
    *,
    user_id: str,
) -> ImageGenerationOptionsRead:
    """返回当前用户默认图片模型对应的关键帧比例/像素规格选项。"""
    settings = await get_or_create_settings(db, user_id=user_id)
    model_id = settings.default_image_model_id
    if not model_id:
        return ImageGenerationOptionsRead(
            provider="",
            model_id="",
            model_name="",
            supported_ratios=sorted(DEFAULT_VIDEO_REFERENCE_RATIO_SIZE_MAP.keys()),
            default_resolution_profile="standard",
            ratio_size_profiles=DEFAULT_VIDEO_REFERENCE_RATIO_SIZE_MAP,
        )

    model = await get_or_404(db, Model, model_id, detail=entity_not_found("Model"))
    provider = await get_or_404(db, Provider, model.provider_id, detail=entity_not_found("Provider"))
    provider_key = resolve_provider_key_from_name(provider.name)
    capability = resolve_image_capability(provider=provider_key, model=model.name)
    ratio_size_profiles = capability.ratio_size_profiles or DEFAULT_VIDEO_REFERENCE_RATIO_SIZE_MAP
    supported_ratios = sorted(capability.supported_ratios or ratio_size_profiles.keys())

    return ImageGenerationOptionsRead(
        provider=provider_key,
        model_id=model.id,
        model_name=model.name,
        supported_ratios=supported_ratios,
        default_resolution_profile=capability.default_resolution_profile or "standard",
        ratio_size_profiles=ratio_size_profiles,
    )


def list_supported_providers(*, category: ModelCategoryKey | None) -> list[ProviderSupportedRead]:
    # 防御性初始化：保证在非应用生命周期上下文（如单测）下也可返回内置清单。
    bootstrap_all_registries()
    specs = list_registered_providers(category=category)
    return [
        ProviderSupportedRead(
            key=spec.key,
            display_name=spec.display_name,
            aliases=list(spec.aliases),
            supported_categories=list(spec.supported_categories),
            default_base_url=spec.default_base_url,
            requires_api_key=spec.requires_api_key,
            requires_api_secret=spec.requires_api_secret,
            is_experimental=spec.is_experimental,
        )
        for spec in specs
    ]


def _ensure_provider_supports_category(*, provider: Provider, category: ModelCategoryKey | str) -> None:
    bootstrap_all_registries()
    normalized_category = (
        category
        if isinstance(category, ModelCategoryKey)
        else ModelCategoryKey((str(category or "")).strip().lower())
    )
    provider_key = resolve_provider_key_from_name(provider.name)
    if not is_provider_category_supported(provider_key, normalized_category):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider {provider.name!r} does not support category={normalized_category.value}",
        )
