"""Studio 实体主资源 CRUD。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.models.studio import Actor, Chapter, Costume, ProjectCharacterLink, Shot, ShotCharacterLink
from app.schemas.studio.cast import ShotCharacterLinkCreate
from app.services.common import entity_already_exists, entity_not_found
from app.services.studio.entity_specs import DEFAULT_VIEW_ANGLES, LINK_MODEL_BY_ENTITY, entity_spec, normalize_entity_type
from app.services.studio.entity_thumbnails import resolve_thumbnails
from app.services.studio.shot_character_links import upsert as upsert_shot_character_link
from app.utils.project_links import upsert_project_link

ENTITY_ORDER_FIELDS = {"name", "style", "visual_style", "created_at", "updated_at"}
# 直接归属用户的资产类型：模型自身带 user_id 列，按用户隔离/判重。
USER_OWNED_ENTITY_TYPES = {"actor", "character", "scene", "prop", "costume"}
# 历史命名保留：原"全局判重"集合即现在的"按用户判重"集合。
GLOBAL_NAME_UNIQUE_ENTITY_TYPES = USER_OWNED_ENTITY_TYPES


def _asset_read_payload(obj: Any, thumbnail: str) -> dict[str, Any]:
    return {
        "id": obj.id,
        "name": obj.name,
        "description": obj.description,
        "tags": obj.tags or [],
        "prompt_template_id": obj.prompt_template_id,
        "view_count": obj.view_count,
        "style": obj.style,
        "visual_style": obj.visual_style,
        "thumbnail": thumbnail,
    }


async def _ensure_user_name_available(
    db: AsyncSession,
    *,
    entity_type: str,
    model: type,
    user_id: str,
    name: str | None,
    exclude_id: str | None = None,
) -> None:
    """在写库前校验当前用户内资产名称唯一性，避免数据库唯一约束异常泄漏到业务流程。

    资产唯一约束已收紧为 `(user_id, name)`，因此判重也限定在当前用户范围内——
    不同用户允许使用同名资产。
    """
    normalized_name = str(name or "").strip()
    if entity_type not in USER_OWNED_ENTITY_TYPES or not normalized_name:
        return

    stmt = select(model.id).where(model.name == normalized_name, model.user_id == user_id)
    if exclude_id:
        stmt = stmt.where(model.id != exclude_id)
    existing_id = (await db.execute(stmt.limit(1))).scalars().first()
    if existing_id is not None:
        raise HTTPException(status_code=409, detail=f"{model.__name__} name already exists: {normalized_name}")


async def _ensure_owned_reference(db: AsyncSession, model: type, entity_id: str, *, user_id: str) -> None:
    """校验角色引用的演员/服装资产存在且归属当前用户。"""

    obj = await db.get(model, entity_id)
    if obj is None or getattr(obj, "user_id", None) != user_id:
        raise HTTPException(status_code=400, detail=entity_not_found(model.__name__))


async def list_entities_paginated(
    db: AsyncSession,
    *,
    entity_type: str,
    user_id: str,
    q: str | None,
    style: str | None,
    visual_style: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
    project_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    stmt = select(spec.model)
    # 所有资产类型（含 character）均有 user_id，按用户隔离。
    if entity_type_norm in USER_OWNED_ENTITY_TYPES:
        stmt = stmt.where(spec.model.user_id == user_id)
    # 按项目过滤：character 通过 ProjectCharacterLink 做 EXISTS 子查询；actor 直接匹配字段（兼容旧逻辑）。
    if project_id:
        if entity_type_norm == "character":
            from sqlalchemy import exists as _exists
            stmt = stmt.where(
                _exists().where(
                    ProjectCharacterLink.character_id == spec.model.id,
                    ProjectCharacterLink.project_id == project_id,
                )
            )
        elif entity_type_norm == "actor" and hasattr(spec.model, "project_id"):
            stmt = stmt.where(getattr(spec.model, "project_id") == project_id)
    stmt = apply_keyword_filter(stmt, q=q, fields=[spec.model.name, spec.model.description])
    if style:
        stmt = stmt.where(getattr(spec.model, "style") == style)
    if visual_style:
        stmt = stmt.where(getattr(spec.model, "visual_style") == visual_style)
    stmt = apply_order(
        stmt,
        model=spec.model,
        order=order,
        is_desc=is_desc,
        allow_fields=ENTITY_ORDER_FIELDS,
        default="created_at",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)

    thumbnails = await resolve_thumbnails(
        db,
        image_model=spec.image_model,
        parent_field_name=spec.id_field,
        parent_ids=[item.id for item in items],
    )
    payload: list[dict[str, Any]] = []
    for item in items:
        thumbnail = thumbnails.get(item.id, "")
        if entity_type_norm in {"actor", "character"}:
            read_model = spec.read_model
            payload.append(read_model.model_validate(item).model_copy(update={"thumbnail": thumbnail}).model_dump())
        else:
            payload.append(_asset_read_payload(item, thumbnail))
    return payload, total


async def create_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    user_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    parsed = spec.create_model.model_validate(body)
    data = parsed.model_dump()

    link_project_id: str | None = None
    link_chapter_id: str | None = None
    link_shot_id: str | None = None
    # character 已加入 LINK_MODEL_BY_ENTITY，与 actor/scene/prop/costume 统一走 upsert_project_link
    if entity_type_norm in LINK_MODEL_BY_ENTITY:
        link_project_id = data.pop("project_id", None)
        link_chapter_id = data.pop("chapter_id", None)
        link_shot_id = data.pop("shot_id", None)

    exists = await db.get(spec.model, data["id"])
    if exists is not None:
        raise HTTPException(status_code=400, detail=entity_already_exists(spec.model.__name__))
    await _ensure_user_name_available(
        db,
        entity_type=entity_type_norm,
        model=spec.model,
        user_id=user_id,
        name=data.get("name"),
    )

    if entity_type_norm == "character":
        # project/chapter/shot 的存在性与归属校验由 upsert_project_link 统一负责
        if data.get("actor_id"):
            await _ensure_owned_reference(db, Actor, str(data["actor_id"]), user_id=user_id)
        if data.get("costume_id"):
            await _ensure_owned_reference(db, Costume, str(data["costume_id"]), user_id=user_id)

    # 资产类型写入归属用户；character 无 user_id 列，不注入。
    if entity_type_norm in USER_OWNED_ENTITY_TYPES:
        data["user_id"] = user_id
    obj = spec.model(**data)
    db.add(obj)
    await db.flush()
    await db.refresh(obj)

    # character 也创建正面视角图片槽位，与 actor/scene/prop/costume 保持一致；
    # view_count 在角色上未使用，固定创建 1 个正面槽位即可
    if entity_type_norm in {"actor", "character", "scene", "prop", "costume"}:
        count = int(getattr(obj, "view_count", 1) or 1)
        angles = list(DEFAULT_VIEW_ANGLES[: min(max(count, 0), len(DEFAULT_VIEW_ANGLES))])
        for angle in angles:
            db.add(spec.image_model(**{spec.id_field: obj.id, "view_angle": angle}))
        if angles:
            await db.flush()

    if link_project_id is not None and entity_type_norm in LINK_MODEL_BY_ENTITY:
        link_model, asset_field = LINK_MODEL_BY_ENTITY[entity_type_norm]
        await upsert_project_link(
            db,
            model=link_model,
            asset_field=asset_field,  # type: ignore[arg-type]
            asset_id=obj.id,
            project_id=link_project_id,
            chapter_id=link_chapter_id,
            shot_id=link_shot_id,
        )

    if entity_type_norm == "character" and link_shot_id is not None:
        existing_indexes_stmt = (
            select(ShotCharacterLink.index)
            .where(ShotCharacterLink.shot_id == link_shot_id)
            .order_by(ShotCharacterLink.index.desc())
            .limit(1)
        )
        max_index = (await db.execute(existing_indexes_stmt)).scalars().first()
        # 追加语义：新建角色挂到镜头时只顺延 index，不踢掉镜头内已关联的其它角色
        await upsert_shot_character_link(
            db,
            reassign_index_on_conflict=True,
            body=ShotCharacterLinkCreate(
                shot_id=link_shot_id,
                character_id=obj.id,
                index=(max_index if isinstance(max_index, int) else -1) + 1,
                note="",
            ),
        )

    if entity_type_norm in {"actor", "character"}:
        read_model = spec.read_model
        payload = read_model.model_validate(obj).model_dump()
        payload["thumbnail"] = ""
        return payload
    return _asset_read_payload(obj, "")


async def get_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    user_id: str,
    entity_id: str,
) -> dict[str, Any]:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    obj = await db.get(spec.model, entity_id)
    # 归属不符按"未找到"处理，避免泄漏他人资产是否存在。
    if obj is None or (entity_type_norm in USER_OWNED_ENTITY_TYPES and obj.user_id != user_id):
        raise HTTPException(status_code=404, detail=entity_not_found(spec.model.__name__))

    thumbnails = await resolve_thumbnails(
        db,
        image_model=spec.image_model,
        parent_field_name=spec.id_field,
        parent_ids=[entity_id],
    )
    thumbnail = thumbnails.get(entity_id, "")
    if entity_type_norm in {"actor", "character"}:
        read_model = spec.read_model
        return read_model.model_validate(obj).model_copy(update={"thumbnail": thumbnail}).model_dump()
    return _asset_read_payload(obj, thumbnail)


async def update_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    user_id: str,
    entity_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    obj = await db.get(spec.model, entity_id)
    # 归属不符按"未找到"处理。
    if obj is None or (entity_type_norm in USER_OWNED_ENTITY_TYPES and obj.user_id != user_id):
        raise HTTPException(status_code=404, detail=entity_not_found(spec.model.__name__))

    update_data = spec.update_model.model_validate(body).model_dump(exclude_unset=True)
    await _ensure_user_name_available(
        db,
        entity_type=entity_type_norm,
        model=spec.model,
        user_id=user_id,
        name=update_data.get("name"),
        exclude_id=entity_id,
    )
    if entity_type_norm == "character":
        if "actor_id" in update_data and update_data["actor_id"] is not None:
            await _ensure_owned_reference(db, Actor, str(update_data["actor_id"]), user_id=user_id)
        if "costume_id" in update_data and update_data["costume_id"] is not None:
            await _ensure_owned_reference(db, Costume, str(update_data["costume_id"]), user_id=user_id)

    for key, value in update_data.items():
        setattr(obj, key, value)
    await db.flush()
    await db.refresh(obj)

    if entity_type_norm in {"actor", "character"}:
        read_model = spec.read_model
        payload = read_model.model_validate(obj).model_dump()
        payload["thumbnail"] = ""
        return payload
    return _asset_read_payload(obj, "")


async def delete_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    user_id: str,
    entity_id: str,
) -> None:
    entity_type_norm = normalize_entity_type(entity_type)
    spec = entity_spec(entity_type_norm)
    obj = await db.get(spec.model, entity_id)
    # 不存在或归属他人时静默返回（删除幂等，不泄漏他人资产）。
    if obj is None or (entity_type_norm in USER_OWNED_ENTITY_TYPES and obj.user_id != user_id):
        return
    await db.delete(obj)
    await db.flush()
