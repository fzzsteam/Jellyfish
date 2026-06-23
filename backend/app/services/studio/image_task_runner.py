from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_maker
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.core.contracts.image_generation import ImageGenerationInput, ImageGenerationResult
from app.core.contracts.provider import ProviderConfig
from app.core.tasks import ImageGenerationTask
from app.models.studio import (
    ActorImage,
    AssetQualityLevel,
    AssetViewAngle,
    CharacterImage,
    CostumeImage,
    PropImage,
    SceneImage,
    ShotDetail,
    ShotFrameImage,
)
from app.models.task_links import GenerationTaskLink
from app.models.types import FileUsageKind
from app.services.studio.file_usages import (
    first_project_id_for_actor,
    first_project_id_for_costume,
    first_project_id_for_prop,
    first_project_id_for_scene,
    sync_usage_from_character,
    sync_usage_from_shot_context,
    upsert_file_usage,
)
from app.services.studio.asset_image_candidates import attach_asset_image_candidate
from app.services.studio.shot_status import mark_shot_generating, recompute_shot_status
from app.services.studio.image_tasks import load_provider_config, resolve_image_model
from app.services.worker.async_task_support import cancel_if_requested_async
from app.services.worker.task_logging import log_task_event, log_task_failure
from app.utils.files import create_file_from_url_or_b64


class _CreateOnlyTask:
    """仅用于 TaskManager.create：提供 __class__.__name__，避免传入 lambda。"""

    async def run(self, *args: object, **kwargs: object):  # noqa: ANN001, ANN003
        return None

    async def status(self) -> dict[str, object]:
        return {}

    async def is_done(self) -> bool:
        return False

    async def get_result(self) -> object:
        return None


async def _persist_images_to_assets(
    session: AsyncSession,
    *,
    task_id: str,
    user_id: str,
    relation_type: str,
    relation_entity_id: str,
    result: ImageGenerationResult,
) -> None:
    """将图片生成结果按任务所属用户落库到 FileItem 与业务图片表。"""
    images = result.images or []
    if not images:
        return

    target = await _resolve_generated_image_target(session, relation_type=relation_type, relation_entity_id=relation_entity_id)
    if target is None:
        return

    target_type, target_id = target
    created_file_ids: list[str] = []
    for index, item in enumerate(images):
        if not item.url:
            continue
        file_obj = await create_file_from_url_or_b64(
            session,
            user_id=user_id,
            url=item.url,
            name=f"{target_type}-{target_id}-{index + 1}",
            prefix=f"generated-images/{target_type}/{target_id}",
        )
        file_id = file_obj.id
        created_file_ids.append(file_id)
        await attach_asset_image_candidate(
            session,
            target_type=target_type,
            target_id=target_id,
            file_id=file_id,
            source_type="generation",
            source_ref=task_id,
            auto_adopt_if_empty=index == 0,
        )
        await _sync_generated_image_usage(
            session,
            relation_type=relation_type,
            relation_entity_id=relation_entity_id,
            target_type=target_type,
            target_id=target_id,
            file_id=file_id,
        )

    if not created_file_ids:
        return

    link_stmt = (
        select(GenerationTaskLink)
        .where(
            GenerationTaskLink.task_id == task_id,
            GenerationTaskLink.relation_type == relation_type,
            GenerationTaskLink.relation_entity_id == relation_entity_id,
        )
        .limit(1)
    )
    link_row = (await session.execute(link_stmt)).scalars().first()
    if link_row is not None:
        link_row.file_id = created_file_ids[0]


async def _resolve_generated_image_target(
    session: AsyncSession,
    *,
    relation_type: str,
    relation_entity_id: str,
) -> tuple[str, int] | None:
    """把生成任务关联关系解析为可挂载候选图的图片槽位。"""
    if relation_type == "actor_image":
        image_row = await session.get(ActorImage, int(relation_entity_id))
        return ("actor_image", image_row.id) if image_row is not None else None
    if relation_type == "scene_image":
        image_row = await session.get(SceneImage, int(relation_entity_id))
        return ("scene_image", image_row.id) if image_row is not None else None
    if relation_type == "prop_image":
        image_row = await session.get(PropImage, int(relation_entity_id))
        return ("prop_image", image_row.id) if image_row is not None else None
    if relation_type == "costume_image":
        image_row = await session.get(CostumeImage, int(relation_entity_id))
        return ("costume_image", image_row.id) if image_row is not None else None
    if relation_type == "character_image":
        image_row = await session.get(CharacterImage, int(relation_entity_id))
        return ("character_image", image_row.id) if image_row is not None else None
    if relation_type == "character":
        character_id = relation_entity_id
        stmt_ci = (
            select(CharacterImage)
            .where(
                CharacterImage.character_id == character_id,
                CharacterImage.quality_level == AssetQualityLevel.low,
                CharacterImage.view_angle == AssetViewAngle.front,
            )
            .order_by(CharacterImage.id.asc())
            .limit(1)
        )
        ci = (await session.execute(stmt_ci)).scalars().first()
        if ci is None:
            ci = CharacterImage(
                character_id=character_id,
                file_id=None,
                quality_level=AssetQualityLevel.low,
                view_angle=AssetViewAngle.front,
                width=None,
                height=None,
                format="png",
                is_primary=True,
            )
            session.add(ci)
        else:
            ci.format = getattr(ci, "format", "") or "png"

        if ci is not None and getattr(ci, "is_primary", False) is True and getattr(ci, "id", None) is not None:
            stmt_clear = (
                CharacterImage.__table__.update()  # type: ignore[attr-defined]
                .where(CharacterImage.character_id == character_id, CharacterImage.id != ci.id)
                .values(is_primary=False)
            )
            await session.execute(stmt_clear)
        await session.flush()
        return ("character_image", ci.id) if ci is not None else None
    if relation_type == "shot_frame_image":
        image_row = await session.get(ShotFrameImage, int(relation_entity_id))
        return ("shot_frame_image", image_row.id) if image_row is not None else None
    return None


async def _sync_generated_image_usage(
    session: AsyncSession,
    *,
    relation_type: str,
    relation_entity_id: str,
    target_type: str,
    target_id: int,
    file_id: str,
) -> None:
    """为生成图同步 file_usages，便于素材库和项目文件页追踪来源。"""
    if target_type == "actor_image":
        image_row = await session.get(ActorImage, target_id)
        if image_row is None:
            return
        pid = await first_project_id_for_actor(session, image_row.actor_id)
        if pid:
            await upsert_file_usage(
                session,
                file_id=file_id,
                project_id=pid,
                chapter_id=None,
                shot_id=None,
                usage_kind=FileUsageKind.asset_image,
                source_ref=f"actor_image:{image_row.id}",
            )
    elif target_type == "scene_image":
        image_row = await session.get(SceneImage, target_id)
        if image_row is None:
            return
        pid = await first_project_id_for_scene(session, image_row.scene_id)
        if pid:
            await upsert_file_usage(
                session,
                file_id=file_id,
                project_id=pid,
                chapter_id=None,
                shot_id=None,
                usage_kind=FileUsageKind.asset_image,
                source_ref=f"scene_image:{image_row.id}",
            )
    elif target_type == "prop_image":
        image_row = await session.get(PropImage, target_id)
        if image_row is None:
            return
        pid = await first_project_id_for_prop(session, image_row.prop_id)
        if pid:
            await upsert_file_usage(
                session,
                file_id=file_id,
                project_id=pid,
                chapter_id=None,
                shot_id=None,
                usage_kind=FileUsageKind.asset_image,
                source_ref=f"prop_image:{image_row.id}",
            )
    elif target_type == "costume_image":
        image_row = await session.get(CostumeImage, target_id)
        if image_row is None:
            return
        pid = await first_project_id_for_costume(session, image_row.costume_id)
        if pid:
            await upsert_file_usage(
                session,
                file_id=file_id,
                project_id=pid,
                chapter_id=None,
                shot_id=None,
                usage_kind=FileUsageKind.asset_image,
                source_ref=f"costume_image:{image_row.id}",
            )
    elif target_type == "character_image":
        image_row = await session.get(CharacterImage, target_id)
        character_id = image_row.character_id if image_row is not None else relation_entity_id
        await sync_usage_from_character(
            session,
            file_id=file_id,
            character_id=character_id,
            usage_kind=FileUsageKind.character_image,
            source_ref=f"character_image:{target_id}",
        )
    elif target_type == "shot_frame_image":
        image_row = await session.get(ShotFrameImage, target_id)
        if image_row is None:
            return
        detail = await session.get(ShotDetail, image_row.shot_detail_id)
        if detail is not None:
            await sync_usage_from_shot_context(
                session,
                file_id=file_id,
                shot_id=detail.id,
                usage_kind=FileUsageKind.shot_frame,
                source_ref=f"shot_frame_image:{image_row.id}",
            )


async def _resolve_related_shot_id(
    session: AsyncSession,
    *,
    relation_type: str,
    relation_entity_id: str,
) -> str | None:
    """仅解析和镜头直接相关的生成任务。"""
    if relation_type != "shot_frame_image":
        return None
    image_row = await session.get(ShotFrameImage, int(relation_entity_id))
    if image_row is None:
        return None
    return image_row.shot_detail_id


async def _find_active_image_task(
    db: AsyncSession,
    *,
    relation_type: str,
    relation_entity_id: str,
) -> GenerationTask | None:
    """按业务关联查询任意活动中的图片任务。

    为什么需要：5b 起对图片任务新增「复用进行中任务」语义，避免对同一资产槽位
    重复冻结积分/创建任务。逻辑镜像 `script_processing_tasks._find_active_task`：
    仅判定是否已存在运行中的同类任务，无需排序。
    """
    from app.models.task import GenerationTask, GenerationTaskStatus
    from sqlalchemy import select

    active_statuses = (
        GenerationTaskStatus.pending,
        GenerationTaskStatus.running,
        GenerationTaskStatus.streaming,
    )
    stmt = (
        select(GenerationTask)
        .join(GenerationTaskLink, GenerationTaskLink.task_id == GenerationTask.id)
        .where(
            GenerationTaskLink.relation_type == relation_type,
            GenerationTaskLink.relation_entity_id == relation_entity_id,
            GenerationTask.status.in_(active_statuses),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def create_image_task_and_link(
    *,
    db: AsyncSession,
    user_id: str,
    model_id: str | None,
    relation_type: str,
    relation_entity_id: str,
    prompt: str,
    images: list[dict[str, str]] | None = None,
    target_ratio: str | None = None,
    resolution_profile: str | None = None,
    purpose: str = "generic",
    render_context: dict | None = None,
    quote_token: str | None = None,
) -> str:
    """创建图片生成任务（归属 user_id），并建立任务关联；默认模型按用户解析。

    积分计费（Task 5b）：
    - `quote_token` 非空时，先调用 `freeze_for_task` 冻结积分，并把 `billing_id`
      透传给 `TaskManager.create`；冻结失败（余额不足/报价失效）抛 `PointsDomainError`
      直接上抛到路由层，任务不会被创建。
    - `quote_token` 为空时跳过冻结（向后兼容：存量内部调用方/未计费场景）。
    - 新增「复用进行中任务」检查：同一 `(relation_type, relation_entity_id)` 已有
      pending/running/streaming 任务时，直接返回该任务 ID，不冻结积分也不创建新任务。
    """
    # 1. 复用检查：已有运行中同类任务 → 直接返回，不冻结/不创建。
    existing = await _find_active_image_task(
        db, relation_type=relation_type, relation_entity_id=relation_entity_id
    )
    if existing is not None:
        return existing.id

    # 2. 冻结积分（仅在传入 quote_token 时；freeze_for_task 内部已 COMMIT）。
    billing_id: str | None = None
    if quote_token:
        from app.models.llm import ModelCategoryKey
        from app.services.points.billing import freeze_for_task

        frozen = await freeze_for_task(
            db,
            user_id=user_id,
            quote_token=quote_token,
            business_type="image_generation",
            category=ModelCategoryKey.image,
            model_id=model_id,
            resolution_profile=resolution_profile,
        )
        billing_id = frozen.billing_id

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})

    model = await resolve_image_model(db, model_id, user_id=user_id)
    provider_cfg = await load_provider_config(db, model.provider_id)

    run_args: dict = {
        "provider": provider_cfg.provider,
        "api_key": provider_cfg.api_key,
        "base_url": provider_cfg.base_url,
        "relation_type": relation_type,
        "relation_entity_id": relation_entity_id,
        "input": {
            "prompt": prompt,
            "model": model.name,
            "target_ratio": target_ratio,
            "resolution_profile": resolution_profile,
            "purpose": purpose,
        },
    }
    if images:
        run_args["input"]["images"] = images
    if render_context:
        run_args["render_context"] = render_context

    try:
        task_record = await tm.create(
            task=_CreateOnlyTask(),
            mode=DeliveryMode.async_polling,
            user_id=user_id,
            task_kind="image_generation",
            run_args=run_args,
            billing_id=billing_id,
        )
    except Exception:
        # 任务创建失败：按 5a 契约回滚冻结，避免冻结悬挂。
        if billing_id:
            from app.services.points import unfreeze_frozen

            await unfreeze_frozen(db, user_id=user_id, billing_id=billing_id)
        raise

    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="image",
            relation_type=relation_type,
            relation_entity_id=relation_entity_id,
        )
    )
    related_shot_id = await _resolve_related_shot_id(
        db,
        relation_type=relation_type,
        relation_entity_id=relation_entity_id,
    )
    if related_shot_id:
        await mark_shot_generating(db, shot_id=related_shot_id)
    await db.commit()

    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_record.id)
    return task_record.id


async def run_image_generation_task(
    task_id: str,
    run_args: dict,
) -> None:
    """执行图片生成，并以任务记录的用户归属持久化所有生成文件。"""
    relation_type = str(run_args.get("relation_type") or "")
    relation_entity_id = str(run_args.get("relation_entity_id") or "")

    async with async_session_maker() as session:
        try:
            store = SqlAlchemyTaskStore(session)
            task_record = await store.get(task_id)
            user_id = (task_record.user_id or "").strip() if task_record is not None else ""
            if not user_id:
                raise RuntimeError(f"Image generation task has no owner: {task_id}")
            await store.set_status(task_id, TaskStatus.running)
            await store.set_progress(task_id, 10)
            await session.commit()
            log_task_event("image_generation", task_id, "running")
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("image_generation", task_id, "cancelled", stage="before_execute")
                return

            provider = str(run_args.get("provider") or "")
            api_key = str(run_args.get("api_key") or "")
            base_url = run_args.get("base_url")
            input_dict = dict(run_args.get("input") or {})

            task = ImageGenerationTask(
                provider_config=ProviderConfig(
                    provider=provider,  # type: ignore[arg-type]
                    api_key=api_key,
                    base_url=base_url,
                ),
                input_=ImageGenerationInput.model_validate(input_dict),
            )
            await task.run()
            result = await task.get_result()
            if result is None:
                status_dict = await task.status()
                detailed_error = ""
                if isinstance(status_dict, dict):
                    detailed_error = str(status_dict.get("error") or "")
                msg = detailed_error or "Image generation task returned no result"
                raise RuntimeError(msg)
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("image_generation", task_id, "cancelled", stage="after_execute")
                return

            result_payload = result.model_dump()
            render_context = run_args.get("render_context")
            if isinstance(render_context, dict):
                result_payload["render_context"] = render_context
            await store.set_result(task_id, result_payload)
            await _persist_images_to_assets(
                session,
                task_id=task_id,
                user_id=user_id,
                relation_type=relation_type,
                relation_entity_id=relation_entity_id,
                result=result,
            )
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("image_generation", task_id, "cancelled", stage="after_persist")
                return
            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            related_shot_id = await _resolve_related_shot_id(
                session,
                relation_type=relation_type,
                relation_entity_id=relation_entity_id,
            )
            if related_shot_id:
                await recompute_shot_status(session, shot_id=related_shot_id)
            await session.commit()
            log_task_event("image_generation", task_id, "succeeded")
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            async with async_session_maker() as s2:
                store = SqlAlchemyTaskStore(s2)
                await store.set_error(task_id, str(exc))
                await store.set_status(task_id, TaskStatus.failed)
                related_shot_id = await _resolve_related_shot_id(
                    s2,
                    relation_type=relation_type,
                    relation_entity_id=relation_entity_id,
                )
                if related_shot_id:
                    await recompute_shot_status(s2, shot_id=related_shot_id)
                await s2.commit()
            log_task_failure("image_generation", task_id, str(exc))
