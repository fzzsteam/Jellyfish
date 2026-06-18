from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import AssetQualityLevel, AssetViewAngle, FileItem, ProjectStyle, ProjectVisualStyle, Scene, SceneImage
from app.services.studio.asset_image_candidates import (
    adopt_asset_image_candidate,
    attach_asset_image_candidate,
    delete_asset_image_candidate,
    list_asset_image_candidates,
)


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


def _file(file_id: str) -> FileItem:
    return FileItem(id=file_id, type="image", name=f"{file_id}.png", storage_key=f"files/{file_id}.png")


def _scene(scene_id: str) -> Scene:
    return Scene(
        id=scene_id,
        name=f"场景 {scene_id}",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
        view_count=1,
        tags=[],
    )


@pytest.mark.asyncio
async def test_attach_candidate_does_not_overwrite_current_image() -> None:
    db, engine = await _build_session()
    try:
        scene = _scene("scene-1")
        current_file = _file("file-current")
        candidate_file = _file("file-candidate")
        db.add_all([scene, current_file, candidate_file])
        await db.flush()
        image = SceneImage(
            scene_id=scene.id,
            file_id=current_file.id,
            quality_level=AssetQualityLevel.low,
            view_angle=AssetViewAngle.front,
        )
        db.add(image)
        await db.commit()

        candidate = await attach_asset_image_candidate(
            db,
            target_type="scene_image",
            target_id=image.id,
            file_id=candidate_file.id,
            source_type="upload",
            source_ref="manual",
            auto_adopt_if_empty=True,
        )
        await db.commit()

        assert candidate.file_id == candidate_file.id
        refreshed = await db.get(SceneImage, image.id)
        assert refreshed is not None
        assert refreshed.file_id == current_file.id
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_attach_candidate_auto_adopts_when_current_image_is_empty() -> None:
    db, engine = await _build_session()
    try:
        scene = _scene("scene-2")
        candidate_file = _file("file-auto")
        db.add_all([scene, candidate_file])
        await db.flush()
        image = SceneImage(
            scene_id=scene.id,
            file_id=None,
            quality_level=AssetQualityLevel.low,
            view_angle=AssetViewAngle.front,
        )
        db.add(image)
        await db.commit()

        await attach_asset_image_candidate(
            db,
            target_type="scene_image",
            target_id=image.id,
            file_id=candidate_file.id,
            source_type="generation",
            source_ref="task-1",
            auto_adopt_if_empty=True,
        )
        await db.commit()

        refreshed = await db.get(SceneImage, image.id)
        assert refreshed is not None
        assert refreshed.file_id == candidate_file.id
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_adopt_candidate_updates_current_image() -> None:
    db, engine = await _build_session()
    try:
        scene = _scene("scene-3")
        file_obj = _file("file-new")
        db.add_all([scene, file_obj])
        await db.flush()
        image = SceneImage(
            scene_id=scene.id,
            file_id=None,
            quality_level=AssetQualityLevel.low,
            view_angle=AssetViewAngle.front,
        )
        db.add(image)
        await db.commit()

        candidate = await attach_asset_image_candidate(
            db,
            target_type="scene_image",
            target_id=image.id,
            file_id=file_obj.id,
            source_type="generation",
            source_ref="task-2",
            auto_adopt_if_empty=False,
        )
        adopted = await adopt_asset_image_candidate(db, candidate_id=candidate.id)
        await db.commit()

        assert adopted.file_id == file_obj.id
        refreshed = await db.get(SceneImage, image.id)
        assert refreshed is not None
        assert refreshed.file_id == file_obj.id
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_candidates_orders_newest_first() -> None:
    db, engine = await _build_session()
    try:
        scene = _scene("scene-4")
        file_a = _file("file-a")
        file_b = _file("file-b")
        db.add_all([scene, file_a, file_b])
        await db.flush()
        image = SceneImage(
            scene_id=scene.id,
            file_id=None,
            quality_level=AssetQualityLevel.low,
            view_angle=AssetViewAngle.front,
        )
        db.add(image)
        await db.commit()

        await attach_asset_image_candidate(
            db,
            target_type="scene_image",
            target_id=image.id,
            file_id=file_a.id,
            source_type="generation",
            source_ref="task-a",
        )
        second = await attach_asset_image_candidate(
            db,
            target_type="scene_image",
            target_id=image.id,
            file_id=file_b.id,
            source_type="upload",
            source_ref="batch-b",
        )
        await db.commit()

        rows = await list_asset_image_candidates(db, target_type="scene_image", target_id=image.id)
        assert rows[0].id == second.id
        assert [row.file_id for row in rows] == ["file-b", "file-a"]
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_candidate_keeps_adopted_image_protected() -> None:
    db, engine = await _build_session()
    try:
        scene = _scene("scene-5")
        file_obj = _file("file-adopted")
        db.add_all([scene, file_obj])
        await db.flush()
        image = SceneImage(
            scene_id=scene.id,
            file_id=None,
            quality_level=AssetQualityLevel.low,
            view_angle=AssetViewAngle.front,
        )
        db.add(image)
        await db.commit()

        candidate = await attach_asset_image_candidate(
            db,
            target_type="scene_image",
            target_id=image.id,
            file_id=file_obj.id,
            source_type="generation",
            source_ref="task-protected",
            auto_adopt_if_empty=True,
        )
        await db.commit()

        with pytest.raises(Exception):
            await delete_asset_image_candidate(db, candidate_id=candidate.id)
    finally:
        await db.close()
        await engine.dispose()
