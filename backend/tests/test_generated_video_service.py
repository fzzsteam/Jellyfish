from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.contracts.video_generation import VideoGenerationResult
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider, ProviderStatus
from app.models.studio import (
    AssetViewAngle,
    CameraAngle,
    CameraMovement,
    CameraShotType,
    Chapter,
    Character,
    CharacterImage,
    Costume,
    CostumeImage,
    FileItem,
    Project,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    ProjectStyle,
    ProjectVisualStyle,
    Prop,
    PropImage,
    Scene,
    SceneImage,
    Shot,
    ShotCharacterLink,
    ShotDetail,
    ShotFrameImage,
    ShotFrameType,
    VFXType,
)
from app.models.types import FileType
from app.services.film.generated_video import (
    build_run_args,
    persist_generated_video_to_shot,
    preview_prompt_and_images,
    resolve_default_video_model,
    run_video_generation_task,
    validate_images_count,
)
from app.bootstrap import bootstrap_all_registries
from app.services.llm import resolve_provider_key_from_name
from app.services.studio.generation.video.derive_preview import derive_video_preview
from app.services.studio.generation.video.build_base import VideoBaseDraft
from app.services.studio.generation.video.build_context import VideoGenerationContext
from app.services.studio import get_shot_video_readiness
from app.models.user import User


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_shot_graph(db: AsyncSession) -> None:
    db.add(User(id="test-user", username="test-user", hashed_password="x"))
    project = Project(
        id="p1",
        name="项目一",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
        user_id="test-user",
    )
    chapter = Chapter(id="c1", project_id="p1", index=1, title="第一章")
    prev_shot = Shot(id="s0", chapter_id="c1", index=0, title="镜头零", script_excerpt="角色沿着墙边逼近门口。")
    shot = Shot(id="s1", chapter_id="c1", index=1, title="镜头一", script_excerpt="角色推门而入。")
    next_shot = Shot(id="s2", chapter_id="c1", index=2, title="镜头二", script_excerpt="角色停下脚步，盯向走廊尽头。")
    prev_detail = ShotDetail(
        id="s0",
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.dolly_in,
        duration=4,
        description="主角贴墙缓慢逼近门口，视线紧盯前方。",
    )
    detail = ShotDetail(
        id="s1",
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        duration=6,
        follow_atmosphere=True,
        vfx_type=VFXType.none,
        description="角色推门后微微停顿，确认走廊内部情况，再向前迈出一步。",
        first_frame_prompt="首帧提示词",
        last_frame_prompt="尾帧提示词",
        key_frame_prompt="关键帧提示词",
    )
    next_detail = ShotDetail(
        id="s2",
        camera_shot=CameraShotType.cu,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        duration=3,
        description="角色停住动作，盯向走廊尽头，情绪绷紧。",
    )
    db.add_all([project, chapter, prev_shot, shot, next_shot, prev_detail, detail, next_detail])
    await db.commit()


@pytest.mark.asyncio
async def test_validate_images_count_rejects_wrong_count() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_images_count("first_last", ["only-one"])

    assert exc_info.value.status_code == 400
    assert "requires exactly 2 images" in exc_info.value.detail


def test_resolve_provider_key_from_name_supports_known_aliases() -> None:
    bootstrap_all_registries()
    assert resolve_provider_key_from_name("OpenAI") == "openai"
    assert resolve_provider_key_from_name("火山引擎") == "volcengine"
    assert resolve_provider_key_from_name("Doubao Video") == "volcengine"


@pytest.mark.asyncio
async def test_resolve_default_video_model_requires_video_category() -> None:
    db, engine = await _build_session()
    async with db:
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        wrong_model = Model(id="m1", name="gpt-4o-mini", category=ModelCategoryKey.text, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m1", user_id="test-user")
        db.add_all([provider, wrong_model, settings])
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await resolve_default_video_model(db, user_id="test-user")

        assert exc_info.value.status_code == 503
        assert "not video category" in exc_info.value.detail
    await engine.dispose()


@pytest.mark.asyncio
async def test_preview_prompt_and_images_uses_auto_frame_ids() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        db.add_all(
            [
                ShotFrameImage(shot_detail_id="s1", frame_type=ShotFrameType.first, file_id="f1", format="png"),
                ShotFrameImage(shot_detail_id="s1", frame_type=ShotFrameType.last, file_id="f2", format="png"),
            ]
        )
        await db.commit()

        prompt, images, pack = await preview_prompt_and_images(
            db,
            user_id="test-user",
            shot_id="s1",
            reference_mode="first_last",
            prompt=None,
        )

        assert "镜头标题：镜头一" in prompt
        assert "剧本摘录：角色推门而入。" in prompt
        assert "动作节拍：" in prompt
        assert "上一镜头：" in prompt
        assert "下一镜头目标：" in prompt
        assert "构图锚点：" in prompt
        assert "朝向与视线：" in prompt
        assert images == ["f1", "f2"]
        assert pack is not None
        assert pack["camera"]["duration"] == 6
        assert pack["action_beats"]
        assert "镜头零" in pack["previous_shot_summary"]
        assert "镜头二" in pack["next_shot_goal"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_preview_prompt_and_images_prefers_request_images_when_provided() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        prompt, images, pack = await preview_prompt_and_images(
            db,
            user_id="test-user",
            shot_id="s1",
            reference_mode="first_last",
            prompt="自定义视频提示词",
            images=["manual-first", "manual-last"],
        )

        assert "自定义视频提示词" in prompt
        assert "动作节拍：" in prompt
        assert "连续性要求：" in prompt
        assert images == ["manual-first", "manual-last"]
        assert pack is not None
        assert pack["camera"]["duration"] == 6
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_maps_reference_images(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        run_args = await build_run_args(
            db,
            user_id="test-user",
            shot_id="s1",
            reference_mode="first_last",
            prompt="最终视频提示词",
            images=["img-first", "img-last"],
            ratio="9:16",
        )

        assert run_args["provider"] == "openai"
        assert run_args["api_key"] == "k"
        assert run_args["input"]["model"] == "sora-mini"
        assert run_args["input"]["first_frame_base64"] == "data:image/png;base64,img-first"
        assert run_args["input"]["last_frame_base64"] == "data:image/png;base64,img-last"
        assert run_args["input"]["key_frame_base64"] is None
        assert run_args["input"]["ratio"] == "9:16"
        assert run_args["input"]["seconds"] == 6
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_clamps_legacy_duration_to_studio_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """Video tasks normalize old or external duration values to the current 3-15s studio range."""
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        detail = await db.get(ShotDetail, "s1")
        assert detail is not None
        detail.duration = 30
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        run_args = await build_run_args(
            db,
            user_id="test-user",
            shot_id="s1",
            reference_mode="first_last",
            prompt="final video prompt",
            images=["img-first", "img-last"],
            ratio="16:9",
        )

        assert run_args["input"]["seconds"] == 15
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_uses_explicit_video_model_over_default() -> None:
    """分镜工作室显式选择视频模型时，任务应使用该模型而不是默认视频模型。"""
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        provider = Provider(id="p1", name="Vidu", base_url="https://api.vidu.example", api_key="k", user_id="test-user")
        default_model = Model(
            id="happyhorse-t2v",
            name="happyhorse-1.0-t2v",
            category=ModelCategoryKey.video,
            provider_id="p1",
            user_id="test-user",
        )
        selected_model = Model(
            id="happyhorse-r2v",
            name="happyhorse-1.0-r2v",
            category=ModelCategoryKey.video,
            provider_id="p1",
            user_id="test-user",
        )
        settings = ModelSettings(id=1, default_video_model_id=default_model.id, user_id="test-user")
        db.add_all([provider, default_model, selected_model, settings])
        await db.commit()

        run_args = await build_run_args(
            db,
            user_id="test-user",
            shot_id="s1",
            model_id=selected_model.id,
            reference_mode="text_only",
            prompt="最终视频提示词",
            images=[],
            ratio="9:16",
        )

        assert run_args["input"]["model"] == "happyhorse-1.0-r2v"
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_adds_r2v_asset_reference_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """HappyHorse r2v should receive linked character, scene, and prop images, excluding costumes."""
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        bootstrap_all_registries()
        provider = Provider(id="p1", name="bailian", base_url="https://dashscope.aliyuncs.com", api_key="k", user_id="test-user")
        model = Model(
            id="happyhorse-r2v",
            name="happyhorse-1.0-r2v",
            category=ModelCategoryKey.video,
            provider_id="p1",
            user_id="test-user",
        )
        db.add_all(
            [
                provider,
                model,
                ModelSettings(id=1, default_video_model_id=model.id, user_id="test-user"),
                Character(
                    id="char-1",
                    project_id="p1",
                    name="苏过",
                    description="",
                    style=ProjectStyle.real_people_city,
                    visual_style=ProjectVisualStyle.live_action,
                ),
                Scene(
                    id="scene-1",
                    name="合江楼",
                    description="",
                    style=ProjectStyle.real_people_city,
                    visual_style=ProjectVisualStyle.live_action,
                    user_id="test-user",
                ),
                Prop(
                    id="prop-1",
                    name="纸鸢",
                    description="",
                    style=ProjectStyle.real_people_city,
                    visual_style=ProjectVisualStyle.live_action,
                    user_id="test-user",
                ),
                Costume(
                    id="costume-1",
                    name="青衫",
                    description="",
                    style=ProjectStyle.real_people_city,
                    visual_style=ProjectVisualStyle.live_action,
                    user_id="test-user",
                ),
                FileItem(id="file-char", type=FileType.image, name="char.png", storage_key="char.png", user_id="test-user"),
                FileItem(id="file-scene", type=FileType.image, name="scene.png", storage_key="scene.png", user_id="test-user"),
                FileItem(id="file-prop", type=FileType.image, name="prop.png", storage_key="prop.png", user_id="test-user"),
                FileItem(id="file-costume", type=FileType.image, name="costume.png", storage_key="costume.png", user_id="test-user"),
                ShotCharacterLink(shot_id="s1", character_id="char-1", index=1),
                ProjectSceneLink(project_id="p1", chapter_id="c1", shot_id="s1", scene_id="scene-1"),
                ProjectPropLink(project_id="p1", chapter_id="c1", shot_id="s1", prop_id="prop-1"),
                ProjectCostumeLink(project_id="p1", chapter_id="c1", shot_id="s1", costume_id="costume-1"),
                CharacterImage(character_id="char-1", file_id="file-char", view_angle=AssetViewAngle.front),
                SceneImage(scene_id="scene-1", file_id="file-scene", view_angle=AssetViewAngle.front),
                PropImage(prop_id="prop-1", file_id="file-prop", view_angle=AssetViewAngle.front),
                CostumeImage(costume_id="costume-1", file_id="file-costume", view_angle=AssetViewAngle.front),
            ]
        )
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        run_args = await build_run_args(
            db,
            user_id="test-user",
            shot_id="s1",
            model_id=model.id,
            reference_mode="text_only",
            prompt="最终视频提示词",
            images=[],
            ratio="9:16",
        )

        assert run_args["input"]["model"] == "happyhorse-1.0-r2v"
        assert run_args["input"]["reference_image_base64s"] == [
            "data:image/png;base64,file-char",
            "data:image/png;base64,file-scene",
            "data:image/png;base64,file-prop",
        ]
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_generated_video_assigns_task_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """视频生成文件必须继承任务归属，不能写入空 user_id。"""
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        captured: dict[str, str] = {}

        async def fake_create_file(_session: AsyncSession, *, user_id: str, **_kwargs):
            """记录视频文件创建收到的用户，并返回最小文件对象。"""
            captured["user_id"] = user_id
            return type("File", (), {"id": "video-file-1"})()

        async def fake_sync_usage(*_args, **_kwargs) -> None:
            """隔离与本测试无关的文件使用关系写入。"""
            return None

        monkeypatch.setattr("app.services.film.generated_video.create_file_from_url_or_b64", fake_create_file)
        monkeypatch.setattr("app.services.film.generated_video.sync_usage_from_shot_context", fake_sync_usage)

        await persist_generated_video_to_shot(
            db,
            task_id="video-task-1",
            user_id="owner-1",
            shot_id="s1",
            result=VideoGenerationResult(url="https://example.com/video.mp4", provider="openai"),
            provider="openai",
            api_key="k",
        )

        assert captured["user_id"] == "owner-1"

    await engine.dispose()


@pytest.mark.asyncio
async def test_run_video_generation_task_passes_task_owner_to_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """视频 runner 必须从任务记录读取可信 owner，而不是依赖请求载荷。"""
    captured: dict[str, str | None] = {}

    class FakeTaskStore:
        """提供视频 runner 所需的最小任务存储接口。"""

        def __init__(self, _session: object) -> None:
            """接受 runner 创建存储时传入的会话。"""
            pass

        async def get(self, _task_id: str):
            """返回带可信用户归属的任务记录。"""
            return type("TaskRecord", (), {"user_id": "owner-1"})()

        async def set_status(self, *_args, **_kwargs) -> None:
            """忽略与本测试断言无关的状态写入。"""
            return None

        async def set_progress(self, *_args, **_kwargs) -> None:
            """忽略与本测试断言无关的进度写入。"""
            return None

        async def set_result(self, *_args, **_kwargs) -> None:
            """忽略与本测试断言无关的结果写入。"""
            return None

    class FakeSession:
        """提供 runner 事务边界所需的最小异步会话。"""

        async def commit(self) -> None:
            """模拟事务提交。"""
            return None

        async def rollback(self) -> None:
            """模拟事务回滚。"""
            return None

    class FakeSessionContext:
        """为 runner 提供异步上下文管理器。"""

        async def __aenter__(self) -> FakeSession:
            """进入上下文时返回测试会话。"""
            return FakeSession()

        async def __aexit__(self, *_args) -> bool:
            """退出上下文且不屏蔽异常。"""
            return False

    class FakeVideoTask:
        """绕过供应商调用并返回最小视频结果。"""

        def __init__(self, *_args, **_kwargs) -> None:
            """接受生产代码传入的供应商配置和输入。"""
            pass

        async def run(self) -> None:
            """模拟完成供应商视频生成。"""
            return None

        async def get_result(self) -> VideoGenerationResult:
            """返回可供落库的最小视频结果。"""
            return VideoGenerationResult(url="https://example.com/video.mp4", provider="openai")

    async def fake_cancel(**_kwargs) -> bool:
        """测试路径不触发取消。"""
        return False

    async def fake_persist(*_args, **kwargs):
        """记录 runner 向视频落库层传递的用户归属。"""
        captured["user_id"] = kwargs.get("user_id")
        return type("File", (), {"id": "video-file-1"})()

    async def fake_recompute(*_args, **_kwargs) -> None:
        """隔离与用户归属无关的镜头状态计算。"""
        return None

    monkeypatch.setattr("app.services.film.generated_video.SqlAlchemyTaskStore", FakeTaskStore)
    monkeypatch.setattr("app.services.film.generated_video.async_session_maker", lambda: FakeSessionContext())
    monkeypatch.setattr("app.services.film.generated_video.VideoGenerationTask", FakeVideoTask)
    monkeypatch.setattr("app.services.film.generated_video.cancel_if_requested_async", fake_cancel)
    monkeypatch.setattr("app.services.film.generated_video.persist_generated_video_to_shot", fake_persist)
    monkeypatch.setattr("app.services.film.generated_video.recompute_shot_status", fake_recompute)
    monkeypatch.setattr("app.services.film.generated_video.log_task_event", lambda *_args, **_kwargs: None)

    await run_video_generation_task(
        "video-task-1",
        {
            "provider": "openai",
            "api_key": "k",
            "base_url": None,
            "shot_id": "s1",
            "input": {"prompt": "p", "model": "sora-mini", "ratio": "16:9"},
        },
    )

    assert captured["user_id"] == "owner-1"


@pytest.mark.asyncio
async def test_build_run_args_uses_prompt_pack_when_prompt_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        run_args = await build_run_args(
            db,
            user_id="test-user",
            shot_id="s1",
            reference_mode="text_only",
            prompt=None,
            images=[],
            ratio="16:9",
        )

        assert "镜头标题：镜头一" in run_args["input"]["prompt"]
        assert "动作节拍：" in run_args["input"]["prompt"]
        assert run_args["input"]["ratio"] == "16:9"
        assert run_args["prompt_preview"]["shot_id"] == "s1"
        assert run_args["prompt_preview"]["pack"]["action_beats"]
        assert "镜头零" in run_args["prompt_preview"]["pack"]["previous_shot_summary"]
        assert "镜头二" in run_args["prompt_preview"]["pack"]["next_shot_goal"]
        assert run_args["prompt_preview"]["pack"]["composition_anchor"]
        assert run_args["prompt_preview"]["pack"]["screen_direction_guidance"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_template_render_is_enriched_with_guidance_when_template_omits_it(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)

        async def _fake_template(*_args, **_kwargs):
            return type("Template", (), {"id": "tpl-1", "name": "simple", "content": "镜头标题：{{ title }}"})()

        monkeypatch.setattr(
            "app.services.studio.generation.video.derive_preview._resolve_video_prompt_template",
            _fake_template,
        )

        derived = await derive_video_preview(
            db,
            user_id="test-user",
            base=VideoBaseDraft(shot_id="s1", prompt=""),
            context=VideoGenerationContext(
                shot_id="s1",
                reference_mode="text_only",
                images=[],
                template_id=None,
            ),
        )

        assert "镜头标题：镜头一" in derived.rendered_prompt
        assert "动作节拍：" in derived.rendered_prompt
        assert "连续性要求：" in derived.rendered_prompt
        assert "构图锚点：" in derived.rendered_prompt
        assert "朝向与视线：" in derived.rendered_prompt
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_video_prompt_is_also_enriched_with_guidance() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)

        derived = await derive_video_preview(
            db,
            user_id="test-user",
            base=VideoBaseDraft(shot_id="s1", prompt="手动视频提示词"),
            context=VideoGenerationContext(
                shot_id="s1",
                reference_mode="text_only",
                images=[],
                template_id=None,
            ),
        )

        assert "手动视频提示词" in derived.rendered_prompt
        assert "动作节拍：" in derived.rendered_prompt
        assert "连续性要求：" in derived.rendered_prompt
        assert "构图锚点：" in derived.rendered_prompt
        assert "朝向与视线：" in derived.rendered_prompt
    await engine.dispose()


@pytest.mark.asyncio
async def test_template_render_keeps_existing_guidance_without_duplicate_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)

        async def _fake_template(*_args, **_kwargs):
            return type(
                "Template",
                (),
                {
                    "id": "tpl-2",
                    "name": "guided",
                    "content": "镜头标题：{{ title }}\n连续性要求：{{ continuity_guidance }}",
                },
            )()

        monkeypatch.setattr(
            "app.services.studio.generation.video.derive_preview._resolve_video_prompt_template",
            _fake_template,
        )

        derived = await derive_video_preview(
            db,
            user_id="test-user",
            base=VideoBaseDraft(shot_id="s1", prompt=""),
            context=VideoGenerationContext(
                shot_id="s1",
                reference_mode="text_only",
                images=[],
                template_id=None,
            ),
        )

        assert derived.rendered_prompt.count("连续性要求：") == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_rejects_disabled_provider() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        provider = Provider(
            id="p1",
            name="OpenAI",
            base_url="https://api.openai.com/v1",
            api_key="k",
            status=ProviderStatus.disabled,
            user_id="test-user",
        )
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await build_run_args(
                db,
                user_id="test-user",
                shot_id="s1",
                reference_mode="text_only",
                prompt="最终视频提示词",
                images=[],
                ratio="16:9",
            )

        assert exc_info.value.status_code == 503
        assert "Provider is disabled" in str(exc_info.value.detail)
    await engine.dispose()


@pytest.mark.asyncio
async def test_shot_video_readiness_reports_ready_for_text_only() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        shot = await db.get(Shot, "s1")
        assert shot is not None
        shot.last_extracted_at = datetime.now(timezone.utc)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.flush()

        readiness = await get_shot_video_readiness(db, user_id="test-user", shot_id="s1", reference_mode="text_only")

        assert readiness.ready is True
        assert {item.key: item.ok for item in readiness.checks}["extraction_ready"] is True
        assert {item.key: item.ok for item in readiness.checks}["reference_frames_ready"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_shot_video_readiness_reports_missing_reference_frame() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        shot = await db.get(Shot, "s1")
        assert shot is not None
        shot.last_extracted_at = datetime.now(timezone.utc)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.flush()

        readiness = await get_shot_video_readiness(db, user_id="test-user", shot_id="s1", reference_mode="first")

        checks = {item.key: item for item in readiness.checks}
        assert readiness.ready is False
        assert checks["reference_frames_ready"].ok is False
        assert "first" in checks["reference_frames_ready"].message
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_uses_request_ratio_as_final_value(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        run_args = await build_run_args(
            db,
            user_id="test-user",
            shot_id="s1",
            reference_mode="text_only",
            prompt="最终视频提示词",
            images=[],
            ratio="9:16",
        )

        assert run_args["input"]["ratio"] == "9:16"
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_rejects_missing_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        with pytest.raises(HTTPException) as exc_info:
            await build_run_args(
                db,
                user_id="test-user",
                shot_id="s1",
                reference_mode="text_only",
                prompt="最终视频提示词",
                images=[],
                ratio=None,
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "ratio is required"
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_does_not_read_shot_override_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        detail = await db.get(ShotDetail, "s1")
        assert detail is not None
        detail.override_video_ratio = "9:16"
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        run_args = await build_run_args(
            db,
            user_id="test-user",
            shot_id="s1",
            reference_mode="text_only",
            prompt="最终视频提示词",
            images=[],
            ratio="16:9",
        )

        assert run_args["input"]["ratio"] == "16:9"
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_accepts_supported_ratio_without_size(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k", user_id="test-user")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", user_id="test-user")
        settings = ModelSettings(id=1, default_video_model_id="m_video", user_id="test-user")
        db.add_all([provider, model, settings])
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        run_args = await build_run_args(
            db,
            user_id="test-user",
            shot_id="s1",
            reference_mode="text_only",
            prompt="最终视频提示词",
            images=[],
            ratio="9:16",
        )

        assert run_args["input"]["ratio"] == "9:16"
    await engine.dispose()
