"""资产图片候选服务。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import ActorImage, CharacterImage, CostumeImage, FileItem, PropImage, SceneImage, ShotFrameImage
from app.models.studio_image_candidates import AssetImageCandidate

IMAGE_TARGET_MODELS = {
    "actor_image": ActorImage,
    "character_image": CharacterImage,
    "scene_image": SceneImage,
    "prop_image": PropImage,
    "costume_image": CostumeImage,
    "shot_frame_image": ShotFrameImage,
}


async def load_asset_image_target(db: AsyncSession, *, target_type: str, target_id: int):
    """读取候选图所属的图片槽位，并校验目标类型合法。"""
    model = IMAGE_TARGET_MODELS.get(target_type)
    if model is None:
        raise HTTPException(status_code=400, detail=f"Unsupported image target_type: {target_type}")
    obj = await db.get(model, target_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{target_type} not found: {target_id}")
    return obj


async def list_asset_image_candidates(db: AsyncSession, *, target_type: str, target_id: int) -> list[AssetImageCandidate]:
    """按新到旧列出目标图片槽位候选。"""
    await load_asset_image_target(db, target_type=target_type, target_id=target_id)
    stmt = (
        select(AssetImageCandidate)
        .where(AssetImageCandidate.target_type == target_type, AssetImageCandidate.target_id == target_id)
        .order_by(AssetImageCandidate.created_at.desc(), AssetImageCandidate.id.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def attach_asset_image_candidate(
    db: AsyncSession,
    *,
    target_type: str,
    target_id: int,
    file_id: str,
    source_type: str,
    source_ref: str | None = None,
    auto_adopt_if_empty: bool = False,
) -> AssetImageCandidate:
    """把文件加入候选池；只有空槽位且允许自动采用时才写当前图。"""
    target = await load_asset_image_target(db, target_type=target_type, target_id=target_id)
    file_obj = await db.get(FileItem, file_id)
    if file_obj is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

    stmt = select(AssetImageCandidate).where(
        AssetImageCandidate.target_type == target_type,
        AssetImageCandidate.target_id == target_id,
        AssetImageCandidate.file_id == file_id,
    )
    candidate = (await db.execute(stmt)).scalars().first()
    if candidate is None:
        candidate = AssetImageCandidate(
            target_type=target_type,
            target_id=target_id,
            file_id=file_id,
            source_type=source_type,
            source_ref=source_ref,
        )
        db.add(candidate)
        await db.flush()

    if auto_adopt_if_empty and not getattr(target, "file_id", None):
        target.file_id = file_id
    return candidate


async def adopt_asset_image_candidate(db: AsyncSession, *, candidate_id: int) -> AssetImageCandidate:
    """采用候选图为当前图片。"""
    candidate = await db.get(AssetImageCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"AssetImageCandidate not found: {candidate_id}")
    target = await load_asset_image_target(db, target_type=candidate.target_type, target_id=candidate.target_id)
    target.file_id = candidate.file_id
    return candidate


async def delete_asset_image_candidate(db: AsyncSession, *, candidate_id: int) -> None:
    """删除候选关系，不删除底层文件。"""
    candidate = await db.get(AssetImageCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"AssetImageCandidate not found: {candidate_id}")
    target = await load_asset_image_target(db, target_type=candidate.target_type, target_id=candidate.target_id)
    if getattr(target, "file_id", None) == candidate.file_id:
        raise HTTPException(status_code=400, detail="Cannot delete adopted image candidate")
    await db.delete(candidate)


__all__ = [
    "adopt_asset_image_candidate",
    "attach_asset_image_candidate",
    "delete_asset_image_candidate",
    "list_asset_image_candidates",
    "load_asset_image_target",
]
