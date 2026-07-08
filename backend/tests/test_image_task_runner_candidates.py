from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.contracts.image_generation import ImageGenerationResult, ImageItem
from app.core.db import Base
from app.models.task import GenerationDeliveryMode, GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.models.studio import AssetQualityLevel, AssetViewAngle, FileItem, ProjectStyle, ProjectVisualStyle, Scene, SceneImage
from app.services.studio.asset_image_candidates import list_asset_image_candidates
from app.services.studio.image_task_runner import _persist_images_to_assets, run_image_generation_task


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
        user_id="test-user",
    )


def _file(file_id: str) -> FileItem:
    return FileItem(
        id=file_id,
        type="image",
        name=f"{file_id}.png",
        storage_key=f"files/{file_id}.png",
        user_id="test-user",
    )


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
        user_id="test-user",
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
        created_file_user_ids: list[str] = []

        async def fake_create_file(session, *, user_id: str, url: str, name: str, prefix: str):
            """记录图片落库收到的可信任务归属。"""
            file_id = f"file-{len(created_file_ids) + 1}"
            created_file_ids.append(file_id)
            created_file_user_ids.append(user_id)
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
            user_id="test-user",
            relation_type="scene_image",
            relation_entity_id=str(image.id),
            result=result,
        )
        await db.commit()

        rows = await list_asset_image_candidates(db, target_type="scene_image", target_id=image.id)
        refreshed = await db.get(SceneImage, image.id)
        link = await db.get(GenerationTaskLink, 1)
        assert created_file_ids == ["file-1", "file-2", "file-3"]
        assert created_file_user_ids == ["test-user", "test-user", "test-user"]
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

        async def fake_create_file(session, *, user_id: str, url: str, name: str, prefix: str):
            """模拟按用户归属创建新候选文件。"""
            assert user_id == "test-user"
            file_obj = _file("file-new")
            session.add(file_obj)
            await session.flush()
            return file_obj

        monkeypatch.setattr("app.services.studio.image_task_runner.create_file_from_url_or_b64", fake_create_file)

        result = ImageGenerationResult(provider="openai", images=[ImageItem(url="https://example.com/new.png")])
        await _persist_images_to_assets(
            db,
            task_id="task-2",
            user_id="test-user",
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


@pytest.mark.asyncio
async def test_run_image_generation_task_persists_provider_error_when_result_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, engine = await _build_session()
    try:
        task_id = "task-provider-error"
        provider_error = (
            "[BailianImage] SDK failed: status=400, "
            "code=InvalidParameter, message=real provider error"
        )
        db.add(
            GenerationTask(
                id=task_id,
                mode=GenerationDeliveryMode.async_polling,
                task_kind="image_generation",
                status=GenerationTaskStatus.pending,
                progress=0,
                payload={},
                result=None,
                error="",
                user_id="test-user",
            )
        )
        await db.commit()
        await db.close()

        class FailingImageGenerationTask:
            """模拟供应商失败：run 捕获真实错误后只在 status() 暴露。"""

            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            async def run(self) -> None:
                return None

            async def get_result(self) -> None:
                return None

            async def status(self) -> dict[str, str]:
                return {"error": provider_error}

        async_session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr("app.services.studio.image_task_runner.async_session_maker", async_session_local)
        monkeypatch.setattr("app.services.studio.image_task_runner.ImageGenerationTask", FailingImageGenerationTask)

        await run_image_generation_task(
            task_id,
            {
                "provider": "aliyun_bailian",
                "api_key": "test-key",
                "base_url": None,
                "relation_type": "scene_image",
                "relation_entity_id": "1",
                "input": {"prompt": "生成图片", "model": "qwen-image-2.0"},
            },
        )

        async with async_session_local() as verify_db:
            row = await verify_db.get(GenerationTask, task_id)
            assert row is not None
            assert row.status == GenerationTaskStatus.failed
            assert row.error == provider_error
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_image_generation_task_keeps_error_trace_empty_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, engine = await _build_session()
    try:
        task_id = "task-error-trace"
        db.add(
            GenerationTask(
                id=task_id,
                mode=GenerationDeliveryMode.async_polling,
                task_kind="image_generation",
                status=GenerationTaskStatus.pending,
                progress=0,
                payload={},
                result=None,
                error="",
                error_trace="",
                user_id="test-user",
            )
        )
        await db.commit()
        await db.close()

        class ExplodingImageGenerationTask:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            async def run(self) -> None:
                raise RuntimeError("provider exploded")

        async_session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr("app.services.studio.image_task_runner.async_session_maker", async_session_local)
        monkeypatch.setattr("app.services.studio.image_task_runner.ImageGenerationTask", ExplodingImageGenerationTask)

        await run_image_generation_task(
            task_id,
            {
                "provider": "aliyun_bailian",
                "api_key": "test-key",
                "base_url": None,
                "relation_type": "scene_image",
                "relation_entity_id": "1",
                "input": {"prompt": "生成图片", "model": "wan2.7-image-pro"},
            },
        )

        async with async_session_local() as verify_db:
            row = await verify_db.get(GenerationTask, task_id)
            assert row is not None
            assert row.status == GenerationTaskStatus.failed
            assert row.error == "provider exploded"
            assert row.error_trace == ""
    finally:
        await engine.dispose()
