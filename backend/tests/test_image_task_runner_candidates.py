from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.contracts.image_generation import ImageGenerationResult, ImageItem
from app.core.db import Base
from app.models.task import GenerationDeliveryMode, GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.models.studio import AssetQualityLevel, AssetViewAngle, FileItem, ProjectStyle, ProjectVisualStyle, Scene, SceneImage
from app.services.studio.asset_image_candidates import list_asset_image_candidates
from app.services.studio.image_task_runner import _persist_images_to_assets


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


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


def _file(file_id: str) -> FileItem:
    return FileItem(id=file_id, type="image", name=f"{file_id}.png", storage_key=f"files/{file_id}.png")


def _task(task_id: str) -> GenerationTask:
    return GenerationTask(
        id=task_id,
        mode=GenerationDeliveryMode.async_polling,
        task_kind="image_generation",
        status=GenerationTaskStatus.succeeded,
        progress=100,
        payload={},
        result=None,
        error="",
    )


@pytest.mark.asyncio
async def test_persist_images_to_assets_keeps_all_generated_images(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    try:
        scene = _scene("scene-runner-1")
        db.add(scene)
        await db.flush()
        image = SceneImage(
            scene_id=scene.id,
            file_id=None,
            quality_level=AssetQualityLevel.low,
            view_angle=AssetViewAngle.front,
        )
        db.add_all(
            [
                image,
                _task("task-1"),
                GenerationTaskLink(
                    task_id="task-1",
                    resource_type="image",
                    relation_type="scene_image",
                    relation_entity_id="1",
                ),
            ]
        )
        await db.commit()

        created_file_ids: list[str] = []

        async def fake_create_file(session, *, url: str, name: str, prefix: str):
            file_id = f"file-{len(created_file_ids) + 1}"
            created_file_ids.append(file_id)
            file_obj = _file(file_id)
            session.add(file_obj)
            await session.flush()
            return file_obj

        monkeypatch.setattr("app.services.studio.image_task_runner.create_file_from_url_or_b64", fake_create_file)

        result = ImageGenerationResult(
            provider="openai",
            images=[
                ImageItem(url="https://example.com/1.png"),
                ImageItem(url="https://example.com/2.png"),
                ImageItem(url="https://example.com/3.png"),
            ],
        )
        await _persist_images_to_assets(
            db,
            task_id="task-1",
            relation_type="scene_image",
            relation_entity_id=str(image.id),
            result=result,
        )
        await db.commit()

        rows = await list_asset_image_candidates(db, target_type="scene_image", target_id=image.id)
        refreshed = await db.get(SceneImage, image.id)
        link = await db.get(GenerationTaskLink, 1)
        assert created_file_ids == ["file-1", "file-2", "file-3"]
        assert [row.file_id for row in rows] == ["file-3", "file-2", "file-1"]
        assert refreshed is not None
        assert refreshed.file_id == "file-1"
        assert link is not None
        assert link.file_id == "file-1"
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_persist_images_to_assets_does_not_overwrite_existing_current_image(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    try:
        scene = _scene("scene-runner-2")
        current_file = _file("file-current")
        db.add_all([scene, current_file])
        await db.flush()
        image = SceneImage(
            scene_id=scene.id,
            file_id=current_file.id,
            quality_level=AssetQualityLevel.low,
            view_angle=AssetViewAngle.front,
        )
        db.add_all([image, _task("task-2")])
        await db.commit()

        async def fake_create_file(session, *, url: str, name: str, prefix: str):
            file_obj = _file("file-new")
            session.add(file_obj)
            await session.flush()
            return file_obj

        monkeypatch.setattr("app.services.studio.image_task_runner.create_file_from_url_or_b64", fake_create_file)

        result = ImageGenerationResult(provider="openai", images=[ImageItem(url="https://example.com/new.png")])
        await _persist_images_to_assets(
            db,
            task_id="task-2",
            relation_type="scene_image",
            relation_entity_id=str(image.id),
            result=result,
        )
        await db.commit()

        rows = await list_asset_image_candidates(db, target_type="scene_image", target_id=image.id)
        refreshed = await db.get(SceneImage, image.id)
        assert [row.file_id for row in rows] == ["file-new"]
        assert refreshed is not None
        assert refreshed.file_id == "file-current"
    finally:
        await db.close()
        await engine.dispose()
