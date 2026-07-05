"""镜头服务：Shot 的分页查询与 CRUD。"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.models.studio import (
    CameraAngle,
    CameraMovement,
    CameraShotType,
    Chapter,
    Shot,
    ShotCandidateStatus,
    ShotCandidateType,
    ShotDetail,
    ShotDialogueCandidateStatus,
    ShotExtractedCandidate,
    ShotExtractedDialogueCandidate,
    VFXType,
)
from app.schemas.common import ApiResponse, PaginatedData, paginated_response
from app.schemas.studio.shots import ShotCreate, ShotExtractionSummaryRead, ShotRead, ShotUpdate
from app.services.common import (
    create_and_refresh,
    delete_if_exists,
    entity_already_exists,
    entity_not_found,
    ensure_not_exists,
    flush_and_refresh,
    get_or_404,
    patch_model,
    require_entity,
)
from app.services.studio.shot_assets_overview import get_shot_assets_overview


def _build_extraction_state(
    *,
    shot: Shot,
    asset_candidate_total: int,
    dialogue_candidate_total: int,
    pending_asset_count: int,
    pending_dialogue_count: int,
) -> str:
    if shot.skip_extraction:
        return "skipped"
    if shot.last_extracted_at is None:
        return "not_extracted"
    if asset_candidate_total == 0 and dialogue_candidate_total == 0:
        return "extracted_empty"
    if pending_asset_count > 0 or pending_dialogue_count > 0:
        return "extracted_pending"
    return "extracted_resolved"


async def _fetch_extraction_counts_map(
    db: AsyncSession,
    *,
    shot_ids: Iterable[str],
) -> dict[str, dict[str, int]]:
    normalized_ids = [str(shot_id).strip() for shot_id in shot_ids if str(shot_id).strip()]
    if not normalized_ids:
        return {}

    asset_stmt = (
        select(
            ShotExtractedCandidate.shot_id,
            func.count(ShotExtractedCandidate.id),
            func.sum(
                case(
                    (ShotExtractedCandidate.candidate_status == ShotCandidateStatus.pending, 1),
                    else_=0,
                )
            ),
        )
        .where(ShotExtractedCandidate.shot_id.in_(normalized_ids))
        .where(ShotExtractedCandidate.candidate_type != ShotCandidateType.costume)
        .group_by(ShotExtractedCandidate.shot_id)
    )
    dialogue_stmt = (
        select(
            ShotExtractedDialogueCandidate.shot_id,
            func.count(ShotExtractedDialogueCandidate.id),
            func.sum(
                case(
                    (ShotExtractedDialogueCandidate.candidate_status == ShotDialogueCandidateStatus.pending, 1),
                    else_=0,
                )
            ),
        )
        .where(ShotExtractedDialogueCandidate.shot_id.in_(normalized_ids))
        .group_by(ShotExtractedDialogueCandidate.shot_id)
    )

    counts_map: dict[str, dict[str, int]] = {
        shot_id: {
            "asset_candidate_total": 0,
            "dialogue_candidate_total": 0,
            "pending_asset_count": 0,
            "pending_dialogue_count": 0,
        }
        for shot_id in normalized_ids
    }

    for shot_id, total, pending in (await db.execute(asset_stmt)).all():
        counts_map[str(shot_id)]["asset_candidate_total"] = int(total or 0)
        counts_map[str(shot_id)]["pending_asset_count"] = int(pending or 0)

    for shot_id in normalized_ids:
        # 与资产确认面板保持同一口径：真实已关联的同名/同实体资产不再计入待确认。
        # 直接数 pending candidate 会让右侧分镜列表在自动关联后仍显示“待关联”。
        overview = await get_shot_assets_overview(db, shot_id=shot_id)
        counts_map[shot_id]["pending_asset_count"] = int(overview.summary.pending_count or 0)

    for shot_id, total, pending in (await db.execute(dialogue_stmt)).all():
        counts_map[str(shot_id)]["dialogue_candidate_total"] = int(total or 0)
        counts_map[str(shot_id)]["pending_dialogue_count"] = int(pending or 0)

    return counts_map


async def _fetch_duration_map(
    db: AsyncSession,
    *,
    shot_ids: Iterable[str],
) -> dict[str, int]:
    normalized_ids = [str(shot_id).strip() for shot_id in shot_ids if str(shot_id).strip()]
    if not normalized_ids:
        return {}

    stmt = select(ShotDetail.id, ShotDetail.duration).where(ShotDetail.id.in_(normalized_ids))
    return {str(shot_id): int(duration or 0) for shot_id, duration in (await db.execute(stmt)).all()}


def _build_shot_read(
    shot: Shot,
    *,
    extraction_counts: dict[str, int] | None = None,
    duration: int = 0,
) -> ShotRead:
    counts = extraction_counts or {}
    asset_candidate_total = int(counts.get("asset_candidate_total", 0))
    dialogue_candidate_total = int(counts.get("dialogue_candidate_total", 0))
    pending_asset_count = int(counts.get("pending_asset_count", 0))
    pending_dialogue_count = int(counts.get("pending_dialogue_count", 0))
    return ShotRead(
        id=shot.id,
        chapter_id=shot.chapter_id,
        index=shot.index,
        title=shot.title,
        thumbnail=shot.thumbnail or "",
        status=shot.status,
        skip_extraction=bool(shot.skip_extraction),
        script_excerpt=shot.script_excerpt or "",
        generated_video_file_id=shot.generated_video_file_id,
        last_extracted_at=shot.last_extracted_at,
        duration=duration,
        extraction=ShotExtractionSummaryRead(
            state=_build_extraction_state(
                shot=shot,
                asset_candidate_total=asset_candidate_total,
                dialogue_candidate_total=dialogue_candidate_total,
                pending_asset_count=pending_asset_count,
                pending_dialogue_count=pending_dialogue_count,
            ),
            has_extracted=shot.last_extracted_at is not None,
            last_extracted_at=shot.last_extracted_at,
            asset_candidate_total=asset_candidate_total,
            dialogue_candidate_total=dialogue_candidate_total,
            pending_asset_count=pending_asset_count,
            pending_dialogue_count=pending_dialogue_count,
        ),
    )


async def build_shot_read(
    db: AsyncSession,
    *,
    shot: Shot,
) -> ShotRead:
    counts_map = await _fetch_extraction_counts_map(db, shot_ids=[shot.id])
    duration_map = await _fetch_duration_map(db, shot_ids=[shot.id])
    return _build_shot_read(
        shot,
        extraction_counts=counts_map.get(shot.id),
        duration=duration_map.get(shot.id, 0),
    )


async def build_shot_reads(
    db: AsyncSession,
    *,
    shots: list[Shot],
) -> list[ShotRead]:
    shot_ids = [shot.id for shot in shots]
    counts_map = await _fetch_extraction_counts_map(db, shot_ids=shot_ids)
    duration_map = await _fetch_duration_map(db, shot_ids=shot_ids)
    return [
        _build_shot_read(
            shot,
            extraction_counts=counts_map.get(shot.id),
            duration=duration_map.get(shot.id, 0),
        )
        for shot in shots
    ]


async def list_paginated(
    db: AsyncSession,
    *,
    chapter_id: str | None,
    q: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
    allow_fields: set[str],
) -> ApiResponse[PaginatedData[ShotRead]]:
    """分页查询镜头。"""
    stmt = select(Shot)
    if chapter_id is not None:
        stmt = stmt.where(Shot.chapter_id == chapter_id)
    stmt = apply_keyword_filter(stmt, q=q, fields=[Shot.title, Shot.script_excerpt])
    stmt = apply_order(
        stmt,
        model=Shot,
        order=order,
        is_desc=is_desc,
        allow_fields=allow_fields,
        default="index",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response(
        await build_shot_reads(db, shots=items),
        page=page,
        page_size=page_size,
        total=total,
    )


async def create(
    db: AsyncSession,
    *,
    body: ShotCreate,
) -> Shot:
    """创建镜头，并同步创建默认 ShotDetail（与分镜流程保持一致）。"""
    await ensure_not_exists(db, Shot, body.id, detail=entity_already_exists("Shot"))
    await require_entity(db, Chapter, body.chapter_id, detail=entity_not_found("Chapter"), status_code=400)
    shot = Shot(**body.model_dump())
    db.add(shot)
    db.add(ShotDetail(
        id=shot.id,
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        follow_atmosphere=True,
        vfx_type=VFXType.none,
        duration=4,
    ))
    await db.flush()
    await db.refresh(shot)
    return shot


async def get(
    db: AsyncSession,
    *,
    shot_id: str,
) -> Shot:
    """获取镜头。"""
    return await get_or_404(db, Shot, shot_id, detail=entity_not_found("Shot"))


async def update(
    db: AsyncSession,
    *,
    shot_id: str,
    body: ShotUpdate,
) -> Shot:
    """更新镜头。"""
    obj = await get_or_404(db, Shot, shot_id, detail=entity_not_found("Shot"))
    update_data = body.model_dump(exclude_unset=True)
    if "chapter_id" in update_data:
        await require_entity(
            db,
            Chapter,
            update_data["chapter_id"],
            detail=entity_not_found("Chapter"),
            status_code=400,
        )
    patch_model(obj, update_data)
    return await flush_and_refresh(db, obj)


async def delete(
    db: AsyncSession,
    *,
    shot_id: str,
) -> None:
    """删除镜头。"""
    await delete_if_exists(db, Shot, shot_id)
