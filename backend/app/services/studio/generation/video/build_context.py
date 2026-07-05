from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import ShotFrameImage, ShotFrameType
from app.services.studio.generation.shared.types import GenerationContext

REQUIRED_FRAMES_BY_MODE: dict[str, tuple[ShotFrameType, ...]] = {
    "first": (ShotFrameType.first,),
    "last": (ShotFrameType.last,),
    "key": (ShotFrameType.key,),
    "first_last": (ShotFrameType.first, ShotFrameType.last),
    "first_last_key": (ShotFrameType.first, ShotFrameType.last, ShotFrameType.key),
    "text_only": (),
}


def required_image_count(reference_mode: str) -> int:
    return len(REQUIRED_FRAMES_BY_MODE[reference_mode])


def validate_images_count(reference_mode: str, images: list[str]) -> None:
    """校验显式帧参考图数量。

    `text_only` 是无手动帧模式：允许携带第二步已确认资产图片，供 r2v 模型作为默认参考素材。
    """
    if reference_mode == "text_only":
        return
    expected = required_image_count(reference_mode)
    actual = len(images or [])
    if actual != expected:
        raise HTTPException(
            status_code=400,
            detail=f"reference_mode={reference_mode} requires exactly {expected} images, got {actual}",
        )


async def resolve_video_reference_images(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    images: list[str] | None = None,
) -> list[str]:
    normalized = [str(item).strip() for item in (images or []) if str(item).strip()]
    if normalized:
        validate_images_count(reference_mode, normalized)
        return normalized

    required_frames = REQUIRED_FRAMES_BY_MODE[reference_mode]
    if not required_frames:
        return []

    stmt = select(ShotFrameImage).where(
        ShotFrameImage.shot_detail_id == shot_id,
        ShotFrameImage.frame_type.in_(required_frames),
    )
    rows = (await db.execute(stmt)).scalars().all()
    frame_map = {row.frame_type: row for row in rows}

    missing: list[ShotFrameType] = []
    ordered_images: list[str] = []
    for frame_type in required_frames:
        row = frame_map.get(frame_type)
        if row is None or not row.file_id:
            missing.append(frame_type)
            continue
        ordered_images.append(str(row.file_id))

    if missing:
        missing_name = ",".join(item.value for item in missing)
        raise HTTPException(
            status_code=400,
            detail=f"Required frame image is missing: {missing_name}; please generate it first",
        )
    return ordered_images


class VideoGenerationContext(GenerationContext):
    """视频生成的动态上下文。"""

    kind: str = "video"
    shot_id: str
    reference_mode: str
    images: list[str]
    ratio: str | None = None
    template_id: str | None = None


async def build_video_context(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    images: list[str] | None,
    ratio: str | None = None,
    template_id: str | None = None,
) -> VideoGenerationContext:
    """Builds a video generation context after resolving reference images and optional ratio metadata."""
    resolved_images = await resolve_video_reference_images(
        db,
        shot_id=shot_id,
        reference_mode=reference_mode,
        images=images,
    )
    return VideoGenerationContext(
        shot_id=shot_id,
        reference_mode=reference_mode,
        images=resolved_images,
        ratio=(ratio or "").strip() or None,
        template_id=template_id,
    )
