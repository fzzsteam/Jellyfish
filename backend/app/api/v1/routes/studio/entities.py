"""统一实体 CRUD：actor/character/scene/prop/costume。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.common import ApiResponse, PaginatedData, created_response, empty_response, paginated_response, success_response
from app.schemas.studio.entity_existence import (
    EntityNameExistenceCheckRequest,
    EntityNameExistenceCheckResponse,
)
from app.schemas.studio.asset_image_candidates import AssetImageCandidateAttachRequest, AssetImageCandidateRead
from app.services.studio import StudioEntitiesService
from app.services.studio.asset_image_candidates import (
    adopt_asset_image_candidate,
    attach_asset_image_candidate,
    delete_asset_image_candidate,
    list_asset_image_candidates,
    load_asset_image_target,
)

router = APIRouter()


@router.post(
    "/existence-check",
    response_model=ApiResponse[EntityNameExistenceCheckResponse],
    summary="批量检测资产名称是否存在（模糊匹配，不分页）",
)
async def check_entity_names_existence(
    body: EntityNameExistenceCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EntityNameExistenceCheckResponse]:
    service = StudioEntitiesService(db)
    data = await service.check_names_existence(
        project_id=body.project_id,
        shot_id=body.shot_id,
        character_names=body.character_names,
        prop_names=body.prop_names,
        scene_names=body.scene_names,
        costume_names=body.costume_names,
    )
    return success_response(EntityNameExistenceCheckResponse.model_validate(data))


@router.get("/{entity_type}", response_model=ApiResponse[PaginatedData[dict[str, Any]]], summary="统一实体列表（分页）")
async def list_entities(
    entity_type: str,
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None, description="关键字，过滤 name/description"),
    style: str | None = Query(None, description="题材/风格（单值）"),
    visual_style: str | None = Query(None, description="画面表现形式（单值：真人/动漫）"),
    order: str | None = Query(None),
    is_desc: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目过滤（仅对 character 类型有效）"),
) -> ApiResponse[PaginatedData[dict[str, Any]]]:
    service = StudioEntitiesService(db)
    payload, total = await service.list_entities(
        entity_type=entity_type,
        q=q,
        style=style,
        visual_style=visual_style,
        order=order,
        is_desc=is_desc,
        page=page,
        page_size=page_size,
        project_id=project_id,
    )
    return paginated_response(payload, page=page, page_size=page_size, total=total)


@router.post("/{entity_type}", response_model=ApiResponse[dict[str, Any]], status_code=status.HTTP_201_CREATED, summary="统一创建实体")
async def create_entity(
    entity_type: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, Any]]:
    service = StudioEntitiesService(db)
    payload = await service.create_entity(entity_type=entity_type, body=body)
    return created_response(payload)


@router.get("/{entity_type}/{entity_id}", response_model=ApiResponse[dict[str, Any]], summary="统一获取实体")
async def get_entity(entity_type: str, entity_id: str, db: AsyncSession = Depends(get_db)) -> ApiResponse[dict[str, Any]]:
    service = StudioEntitiesService(db)
    payload = await service.get_entity(entity_type=entity_type, entity_id=entity_id)
    return success_response(payload)


@router.patch("/{entity_type}/{entity_id}", response_model=ApiResponse[dict[str, Any]], summary="统一更新实体")
async def update_entity(
    entity_type: str,
    entity_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, Any]]:
    service = StudioEntitiesService(db)
    payload = await service.update_entity(entity_type=entity_type, entity_id=entity_id, body=body)
    return success_response(payload)


@router.delete("/{entity_type}/{entity_id}", response_model=ApiResponse[None], summary="统一删除实体")
async def delete_entity(entity_type: str, entity_id: str, db: AsyncSession = Depends(get_db)) -> ApiResponse[None]:
    service = StudioEntitiesService(db)
    await service.delete_entity(entity_type=entity_type, entity_id=entity_id)
    return empty_response()


@router.get(
    "/{entity_type}/{entity_id}/images",
    response_model=ApiResponse[PaginatedData[dict[str, Any]]],
    summary="统一实体图片列表（分页）",
)
async def list_entity_images(
    entity_type: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    order: str | None = Query(None),
    is_desc: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[dict[str, Any]]]:
    service = StudioEntitiesService(db)
    payload, total = await service.list_entity_images(
        entity_type=entity_type,
        entity_id=entity_id,
        order=order,
        is_desc=is_desc,
        page=page,
        page_size=page_size,
    )
    return paginated_response(payload, page=page, page_size=page_size, total=total)


@router.post(
    "/{entity_type}/{entity_id}/images",
    response_model=ApiResponse[dict[str, Any]],
    status_code=status.HTTP_201_CREATED,
    summary="统一创建实体图片",
)
async def create_entity_image(
    entity_type: str,
    entity_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, Any]]:
    service = StudioEntitiesService(db)
    payload = await service.create_entity_image(entity_type=entity_type, entity_id=entity_id, body=body)
    return created_response(payload)


@router.patch(
    "/{entity_type}/{entity_id}/images/{image_id}",
    response_model=ApiResponse[dict[str, Any]],
    summary="统一更新实体图片",
)
async def update_entity_image(
    entity_type: str,
    entity_id: str,
    image_id: int,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, Any]]:
    service = StudioEntitiesService(db)
    payload = await service.update_entity_image(
        entity_type=entity_type,
        entity_id=entity_id,
        image_id=image_id,
        body=body,
    )
    return success_response(payload)


@router.get(
    "/{entity_type}/{entity_id}/images/{image_id}/candidates",
    response_model=ApiResponse[list[AssetImageCandidateRead]],
    summary="列出实体图片候选",
)
async def list_entity_image_candidates(
    entity_type: str,
    entity_id: str,
    image_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AssetImageCandidateRead]]:
    target_type = f"{entity_type}_image"
    target = await load_asset_image_target(db, target_type=target_type, target_id=image_id)
    rows = await list_asset_image_candidates(db, target_type=target_type, target_id=image_id)
    current_file_id = getattr(target, "file_id", None)
    return success_response(
        [AssetImageCandidateRead.from_candidate(row, current_file_id=current_file_id) for row in rows]
    )


@router.post(
    "/{entity_type}/{entity_id}/images/{image_id}/candidates",
    response_model=ApiResponse[list[AssetImageCandidateRead]],
    status_code=status.HTTP_201_CREATED,
    summary="添加实体图片候选",
)
async def attach_entity_image_candidates(
    entity_type: str,
    entity_id: str,
    image_id: int,
    body: AssetImageCandidateAttachRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AssetImageCandidateRead]]:
    target_type = f"{entity_type}_image"
    rows = []
    for file_id in body.file_ids:
        rows.append(
            await attach_asset_image_candidate(
                db,
                target_type=target_type,
                target_id=image_id,
                file_id=file_id,
                source_type=body.source_type,
                source_ref=body.source_ref,
                auto_adopt_if_empty=body.auto_adopt_if_empty,
            )
        )
    await db.commit()
    target = await load_asset_image_target(db, target_type=target_type, target_id=image_id)
    current_file_id = getattr(target, "file_id", None)
    return created_response(
        [AssetImageCandidateRead.from_candidate(row, current_file_id=current_file_id) for row in rows]
    )


@router.post(
    "/{entity_type}/{entity_id}/images/{image_id}/candidates/{candidate_id}/adopt",
    response_model=ApiResponse[AssetImageCandidateRead],
    summary="采用实体图片候选为当前图",
)
async def adopt_entity_image_candidate(
    entity_type: str,
    entity_id: str,
    image_id: int,
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AssetImageCandidateRead]:
    row = await adopt_asset_image_candidate(db, candidate_id=candidate_id)
    await db.commit()
    return success_response(AssetImageCandidateRead.from_candidate(row, current_file_id=row.file_id))


@router.delete(
    "/{entity_type}/{entity_id}/images/{image_id}/candidates/{candidate_id}",
    response_model=ApiResponse[None],
    summary="删除实体图片候选关系",
)
async def delete_entity_image_candidate(
    entity_type: str,
    entity_id: str,
    image_id: int,
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await delete_asset_image_candidate(db, candidate_id=candidate_id)
    await db.commit()
    return empty_response()


@router.delete(
    "/{entity_type}/{entity_id}/images/{image_id}",
    response_model=ApiResponse[None],
    summary="统一删除实体图片",
)
async def delete_entity_image(
    entity_type: str,
    entity_id: str,
    image_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    service = StudioEntitiesService(db)
    await service.delete_entity_image(entity_type=entity_type, entity_id=entity_id, image_id=image_id)
    return empty_response()
