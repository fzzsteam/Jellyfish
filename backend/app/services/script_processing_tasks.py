from __future__ import annotations

import asyncio
import json
import logging
import traceback
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.agents.script_processing_agents import (
    EntityMergeResult,
    VariantAnalysisResult,
)
from app.core.db import async_session_maker
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.services.llm.resolver import build_default_text_llm
from app.models.task import GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.chains.agents import EntityMergerAgent, VariantAnalyzerAgent


logger = logging.getLogger(__name__)

CHAPTER_DIVISION_RELATION_TYPE = "chapter_division"
SCRIPT_EXTRACTION_RELATION_TYPE = "script_extraction"
ENTITY_MERGE_RELATION_TYPE = "entity_merge"  # 预备能力：当前无真实前端入口
CONSISTENCY_CHECK_RELATION_TYPE = "consistency_check"
VARIANT_ANALYSIS_RELATION_TYPE = "variant_analysis"  # 预备能力：当前无真实前端入口
CHARACTER_PORTRAIT_ANALYSIS_RELATION_TYPE = "character_portrait_analysis"
PROP_INFO_ANALYSIS_RELATION_TYPE = "prop_info_analysis"
SCENE_INFO_ANALYSIS_RELATION_TYPE = "scene_info_analysis"
COSTUME_INFO_ANALYSIS_RELATION_TYPE = "costume_info_analysis"
SCRIPT_OPTIMIZATION_RELATION_TYPE = "script_optimization"
SCRIPT_SIMPLIFICATION_RELATION_TYPE = "script_simplification"
SCRIPT_DIVIDE_TASK_KIND = "script_divide"
SCRIPT_EXTRACT_TASK_KIND = "script_extract"
SCRIPT_MERGE_TASK_KIND = "script_merge"
SCRIPT_CONSISTENCY_TASK_KIND = "script_consistency"
SCRIPT_VARIANT_TASK_KIND = "script_variant"
SCRIPT_CHARACTER_PORTRAIT_TASK_KIND = "script_character_portrait"
SCRIPT_PROP_INFO_TASK_KIND = "script_prop_info"
SCRIPT_SCENE_INFO_TASK_KIND = "script_scene_info"
SCRIPT_COSTUME_INFO_TASK_KIND = "script_costume_info"
SCRIPT_OPTIMIZE_TASK_KIND = "script_optimize"
SCRIPT_SIMPLIFY_TASK_KIND = "script_simplify"
_ACTIVE_TASK_STATUSES = (
    GenerationTaskStatus.pending,
    GenerationTaskStatus.running,
    GenerationTaskStatus.streaming,
)


class _CreateOnlyTask:
    """仅用于 TaskManager.create，避免为异步任务额外声明无意义 task 类。"""

    async def run(self, *args: object, **kwargs: object):
        return None

    async def status(self) -> dict[str, object]:
        return {}

    async def is_done(self) -> bool:
        return False

    async def get_result(self) -> object:
        return None


@dataclass(slots=True)
class AsyncTaskCreateResult:
    task_id: str
    status: TaskStatus
    reused: bool
    relation_type: str
    relation_entity_id: str


async def _cancel_if_requested(
    store: SqlAlchemyTaskStore,
    task_id: str,
    db: AsyncSession,
) -> bool:
    """在阶段边界检查取消请求，并统一完成 cancelled 收尾。"""

    if not await store.is_cancel_requested(task_id):
        return False
    await store.mark_cancelled(task_id)
    await db.commit()
    return True


async def _freeze_for_script_task(
    db: AsyncSession,
    *,
    user_id: str,
    quote_token: str | None,
    business_type: str,
    cascade_group_id: str | None = None,
) -> str | None:
    """脚本类异步任务冻结积分的统一入口（Task 5b）。

    为什么集中：11 个 creator 共用同一套「按 quote_token 冻结 + 失败回滚」逻辑，
    集中到一处避免 11 份拷贝。脚本任务统一走默认文本模型，故 `category=text`、
    `model_id=None`（报价单据内已绑定模型 ID，权威）。

    返回：
    - `quote_token` 为空 → 跳过冻结，返回 None（向后兼容：未计费/内部调用）。
    - 冻结成功 → 返回 `billing_id`，调用方需透传到 `tm.create(billing_id=...)`，
      且若 `tm.create` 后续失败必须调用 `unfreeze_frozen` 回滚（各 creator 自行处理）。
    - 冻结失败 → `freeze_for_task` 抛 `PointsDomainError`，直接上抛到路由层。
    """
    if not quote_token:
        return None
    from app.models.llm import ModelCategoryKey
    from app.services.points.billing import freeze_for_task

    frozen = await freeze_for_task(
        db,
        user_id=user_id,
        quote_token=quote_token,
        business_type=business_type,
        category=ModelCategoryKey.text,
        model_id=None,
        cascade_group_id=cascade_group_id,
    )
    return frozen.billing_id


async def _unfreeze_script_task(db: AsyncSession, *, user_id: str, billing_id: str | None) -> None:
    """任务创建失败时按 5a 契约回滚冻结；billing_id 为空则无操作。"""
    if not billing_id:
        return
    from app.services.points import unfreeze_frozen

    await unfreeze_frozen(db, user_id=user_id, billing_id=billing_id, created_by="system")


async def find_active_divide_task(
    db: AsyncSession,
    *,
    chapter_id: str,
) -> GenerationTask | None:
    return await _find_active_task(
        db,
        relation_type=CHAPTER_DIVISION_RELATION_TYPE,
        relation_entity_id=chapter_id,
    )


async def _find_active_task(
    db: AsyncSession,
    *,
    relation_type: str,
    relation_entity_id: str,
) -> GenerationTask | None:
    """按业务关联查询任意活动任务。

    这里的目标只是“是否已有运行中的同类任务”，不需要挑出“最新”那一条。
    因此直接从 relation link 侧过滤，再按活动状态做一次连接，并去掉排序，
    避免在任务量大时触发 MySQL 的大排序与 sort buffer 压力。
    """
    stmt = (
        select(GenerationTask)
        .join(GenerationTaskLink, GenerationTaskLink.task_id == GenerationTask.id)
        .where(
            GenerationTaskLink.relation_type == relation_type,
            GenerationTaskLink.relation_entity_id == relation_entity_id,
            GenerationTask.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def create_divide_task(
    db: AsyncSession,
    *,
    user_id: str,
    chapter_id: str,
    script_text: str,
    write_to_db: bool,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    existing = await find_active_divide_task(db, chapter_id=chapter_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=CHAPTER_DIVISION_RELATION_TYPE,
            relation_entity_id=chapter_id,
        )

    billing_id = await _freeze_for_script_task(
        db, user_id=user_id, quote_token=quote_token, business_type=SCRIPT_DIVIDE_TASK_KIND
    )
    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    run_args = {
        "chapter_id": chapter_id,
        "script_text": script_text,
        "write_to_db": write_to_db,
    }
    try:
        task_record = await tm.create(
            task=_CreateOnlyTask(),
            mode=DeliveryMode.async_polling,
            user_id=user_id,
            task_kind=SCRIPT_DIVIDE_TASK_KIND,
            run_args=run_args,
            billing_id=billing_id,
        )
    except Exception:
        await _unfreeze_script_task(db, user_id=user_id, billing_id=billing_id)
        raise
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=CHAPTER_DIVISION_RELATION_TYPE,
            relation_entity_id=chapter_id,
        )
    )
    await db.flush()

    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=CHAPTER_DIVISION_RELATION_TYPE,
        relation_entity_id=chapter_id,
    )
def spawn_divide_task(task_id: str) -> None:
    """统一封装后台启动：第一阶段改为通用 Celery 执行入口。"""
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


async def find_active_extract_task(
    db: AsyncSession,
    *,
    chapter_id: str,
) -> GenerationTask | None:
    return await _find_active_task(
        db,
        relation_type=SCRIPT_EXTRACTION_RELATION_TYPE,
        relation_entity_id=chapter_id,
    )


async def find_active_merge_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
) -> GenerationTask | None:
    return await _find_active_task(
        db,
        relation_type=ENTITY_MERGE_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
    )


async def find_active_consistency_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
) -> GenerationTask | None:
    return await _find_active_task(
        db,
        relation_type=CONSISTENCY_CHECK_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
    )


async def find_active_variant_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
) -> GenerationTask | None:
    return await _find_active_task(
        db,
        relation_type=VARIANT_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
    )


async def _find_active_analysis_task(
    db: AsyncSession,
    *,
    relation_type: str,
    relation_entity_id: str,
) -> GenerationTask | None:
    return await _find_active_task(
        db,
        relation_type=relation_type,
        relation_entity_id=relation_entity_id,
    )


def pick_merge_relation_entity_id(*, chapter_id: str | None, project_id: str | None) -> str:
    relation_entity_id = (chapter_id or "").strip() or (project_id or "").strip()
    if not relation_entity_id:
        raise HTTPException(status_code=400, detail="chapter_id or project_id is required for merge-entities-async")
    return relation_entity_id


def pick_consistency_relation_entity_id(*, chapter_id: str | None, project_id: str | None) -> str:
    relation_entity_id = (chapter_id or "").strip() or (project_id or "").strip()
    if not relation_entity_id:
        raise HTTPException(status_code=400, detail="chapter_id or project_id is required for check-consistency-async")
    return relation_entity_id


def pick_variant_relation_entity_id(*, chapter_id: str | None, project_id: str | None) -> str:
    relation_entity_id = (chapter_id or "").strip() or (project_id or "").strip()
    if not relation_entity_id:
        raise HTTPException(status_code=400, detail="chapter_id or project_id is required for analyze-variants-async")
    return relation_entity_id


def pick_analysis_relation_entity_id(
    *,
    relation_entity_id: str | None = None,
    chapter_id: str | None,
    project_id: str | None,
    endpoint: str,
) -> str:
    relation_entity_id = (relation_entity_id or "").strip() or (chapter_id or "").strip() or (project_id or "").strip()
    if not relation_entity_id:
        raise HTTPException(status_code=400, detail=f"relation_entity_id or chapter_id or project_id is required for {endpoint}")
    return relation_entity_id


async def create_extract_task(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str,
    chapter_id: str,
    script_text: str | None = None,
    script_division: dict,
    consistency: dict | None,
    refresh_cache: bool,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    existing = await find_active_extract_task(db, chapter_id=chapter_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=SCRIPT_EXTRACTION_RELATION_TYPE,
            relation_entity_id=chapter_id,
        )

    billing_id = await _freeze_for_script_task(
        db, user_id=user_id, quote_token=quote_token, business_type=SCRIPT_EXTRACT_TASK_KIND
    )
    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    run_args = {
        "project_id": project_id,
        "chapter_id": chapter_id,
        "script_text": script_text or "",
        "script_division": script_division,
        "consistency": consistency,
        "refresh_cache": refresh_cache,
    }
    try:
        task_record = await tm.create(
            task=_CreateOnlyTask(),
            mode=DeliveryMode.async_polling,
            user_id=user_id,
            task_kind=SCRIPT_EXTRACT_TASK_KIND,
            run_args=run_args,
            billing_id=billing_id,
        )
    except Exception:
        await _unfreeze_script_task(db, user_id=user_id, billing_id=billing_id)
        raise
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=SCRIPT_EXTRACTION_RELATION_TYPE,
            relation_entity_id=chapter_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=SCRIPT_EXTRACTION_RELATION_TYPE,
        relation_entity_id=chapter_id,
    )


async def create_merge_task(
    db: AsyncSession,
    *,
    user_id: str,
    relation_entity_id: str,
    project_id: str | None = None,
    chapter_id: str | None = None,
    all_shot_extractions: list[dict],
    historical_library: dict | None,
    script_division: dict | None,
    previous_merge: dict | None,
    conflict_resolutions: list[dict] | None,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    existing = await find_active_merge_task(db, relation_entity_id=relation_entity_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=ENTITY_MERGE_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )

    billing_id = await _freeze_for_script_task(
        db, user_id=user_id, quote_token=quote_token, business_type=SCRIPT_MERGE_TASK_KIND
    )
    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    run_args = {
        "project_id": project_id,
        "chapter_id": chapter_id,
        "all_shot_extractions": all_shot_extractions,
        "historical_library": historical_library,
        "script_division": script_division,
        "previous_merge": previous_merge,
        "conflict_resolutions": conflict_resolutions,
    }
    try:
        task_record = await tm.create(
            task=_CreateOnlyTask(),
            mode=DeliveryMode.async_polling,
            user_id=user_id,
            task_kind=SCRIPT_MERGE_TASK_KIND,
            run_args=run_args,
            billing_id=billing_id,
        )
    except Exception:
        await _unfreeze_script_task(db, user_id=user_id, billing_id=billing_id)
        raise
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=ENTITY_MERGE_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=ENTITY_MERGE_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
    )


async def create_consistency_task(
    db: AsyncSession,
    *,
    user_id: str,
    relation_entity_id: str,
    project_id: str | None = None,
    chapter_id: str | None = None,
    script_text: str,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    existing = await find_active_consistency_task(db, relation_entity_id=relation_entity_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=CONSISTENCY_CHECK_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )

    billing_id = await _freeze_for_script_task(
        db, user_id=user_id, quote_token=quote_token, business_type=SCRIPT_CONSISTENCY_TASK_KIND
    )
    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    try:
        task_record = await tm.create(
            task=_CreateOnlyTask(),
            mode=DeliveryMode.async_polling,
            user_id=user_id,
            task_kind=SCRIPT_CONSISTENCY_TASK_KIND,
            run_args={"project_id": project_id, "chapter_id": chapter_id, "script_text": script_text},
            billing_id=billing_id,
        )
    except Exception:
        await _unfreeze_script_task(db, user_id=user_id, billing_id=billing_id)
        raise
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=CONSISTENCY_CHECK_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=CONSISTENCY_CHECK_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
    )


async def create_variant_task(
    db: AsyncSession,
    *,
    user_id: str,
    relation_entity_id: str,
    project_id: str | None = None,
    chapter_id: str | None = None,
    merged_library: dict,
    all_shot_extractions: list[dict],
    script_division: dict | None,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    existing = await find_active_variant_task(db, relation_entity_id=relation_entity_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=VARIANT_ANALYSIS_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )

    billing_id = await _freeze_for_script_task(
        db, user_id=user_id, quote_token=quote_token, business_type=SCRIPT_VARIANT_TASK_KIND
    )
    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    try:
        task_record = await tm.create(
            task=_CreateOnlyTask(),
            mode=DeliveryMode.async_polling,
            user_id=user_id,
            task_kind=SCRIPT_VARIANT_TASK_KIND,
            run_args={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "merged_library": merged_library,
                "all_shot_extractions": all_shot_extractions,
                "script_division": script_division,
            },
            billing_id=billing_id,
        )
    except Exception:
        await _unfreeze_script_task(db, user_id=user_id, billing_id=billing_id)
        raise
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=VARIANT_ANALYSIS_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=VARIANT_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
    )


async def _create_analysis_task(
    db: AsyncSession,
    *,
    user_id: str,
    task_kind: str,
    relation_type: str,
    relation_entity_id: str,
    run_args: dict,
    project_id: str | None = None,
    chapter_id: str | None = None,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    existing = await _find_active_analysis_task(db, relation_type=relation_type, relation_entity_id=relation_entity_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=relation_type,
            relation_entity_id=relation_entity_id,
        )

    billing_id = await _freeze_for_script_task(
        db, user_id=user_id, quote_token=quote_token, business_type=task_kind
    )
    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    try:
        task_record = await tm.create(
            task=_CreateOnlyTask(),
            mode=DeliveryMode.async_polling,
            user_id=user_id,
            task_kind=task_kind,
            run_args={**run_args, "project_id": project_id, "chapter_id": chapter_id},
            billing_id=billing_id,
        )
    except Exception:
        await _unfreeze_script_task(db, user_id=user_id, billing_id=billing_id)
        raise
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=relation_type,
            relation_entity_id=relation_entity_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=relation_type,
        relation_entity_id=relation_entity_id,
    )


async def create_character_portrait_task(
    db: AsyncSession,
    *,
    user_id: str,
    relation_entity_id: str,
    project_id: str | None = None,
    chapter_id: str | None = None,
    character_context: str | None,
    character_description: str,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        user_id=user_id,
        task_kind=SCRIPT_CHARACTER_PORTRAIT_TASK_KIND,
        relation_type=CHARACTER_PORTRAIT_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "character_context": character_context,
            "character_description": character_description,
        },
        project_id=project_id,
        chapter_id=chapter_id,
        quote_token=quote_token,
    )


async def create_prop_info_task(
    db: AsyncSession,
    *,
    user_id: str,
    relation_entity_id: str,
    project_id: str | None = None,
    chapter_id: str | None = None,
    prop_context: str | None,
    prop_description: str,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        user_id=user_id,
        task_kind=SCRIPT_PROP_INFO_TASK_KIND,
        relation_type=PROP_INFO_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "prop_context": prop_context,
            "prop_description": prop_description,
        },
        project_id=project_id,
        chapter_id=chapter_id,
        quote_token=quote_token,
    )


async def create_scene_info_task(
    db: AsyncSession,
    *,
    user_id: str,
    relation_entity_id: str,
    project_id: str | None = None,
    chapter_id: str | None = None,
    scene_context: str | None,
    scene_description: str,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        user_id=user_id,
        task_kind=SCRIPT_SCENE_INFO_TASK_KIND,
        relation_type=SCENE_INFO_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "scene_context": scene_context,
            "scene_description": scene_description,
        },
        project_id=project_id,
        chapter_id=chapter_id,
        quote_token=quote_token,
    )


async def create_costume_info_task(
    db: AsyncSession,
    *,
    user_id: str,
    relation_entity_id: str,
    project_id: str | None = None,
    chapter_id: str | None = None,
    costume_context: str | None,
    costume_description: str,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        user_id=user_id,
        task_kind=SCRIPT_COSTUME_INFO_TASK_KIND,
        relation_type=COSTUME_INFO_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "costume_context": costume_context,
            "costume_description": costume_description,
        },
        project_id=project_id,
        chapter_id=chapter_id,
        quote_token=quote_token,
    )


async def create_script_optimization_task(
    db: AsyncSession,
    *,
    user_id: str,
    relation_entity_id: str,
    project_id: str | None = None,
    chapter_id: str | None = None,
    script_text: str,
    consistency: dict,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        user_id=user_id,
        task_kind=SCRIPT_OPTIMIZE_TASK_KIND,
        relation_type=SCRIPT_OPTIMIZATION_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "script_text": script_text,
            "consistency": consistency,
        },
        project_id=project_id,
        chapter_id=chapter_id,
        quote_token=quote_token,
    )


async def create_script_simplification_task(
    db: AsyncSession,
    *,
    user_id: str,
    relation_entity_id: str,
    project_id: str | None = None,
    chapter_id: str | None = None,
    script_text: str,
    quote_token: str | None = None,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        user_id=user_id,
        task_kind=SCRIPT_SIMPLIFY_TASK_KIND,
        relation_type=SCRIPT_SIMPLIFICATION_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "script_text": script_text,
        },
        project_id=project_id,
        chapter_id=chapter_id,
        quote_token=quote_token,
    )


def spawn_extract_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


async def run_merge_task(task_id: str) -> None:
    async with async_session_maker() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.get(task_id)
        if task is None:
            logger.warning("merge task not found: %s", task_id)
            return

        # 入口取消：任务尚未进入 running，但用户已请求取消 → 标记 cancelled 并结算。
        # 必须结算（解冻）：merge/variant 经 asyncio.create_task 执行，不走 Celery 的
        # finally 钩子，cancel 路由的立即解冻也不适用（非 Celery executor 无法 revoke），
        # 故每个到达 cancelled 终态的分支都要显式 `await _settle_billing(task_id)`，否则冻结积分泄漏。
        if await _cancel_if_requested(store, task_id, db):
            await _settle_billing(task_id)
            return

        await store.set_status(task_id, TaskStatus.running)
        await store.set_progress(task_id, 5)
        await db.commit()
        run_args = task.payload.get("run_args") or {}
        task_user_id = task.user_id

    try:
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            # try 起点取消：已 running、尚未调用 LLM → 同样必须结算。
            if await _cancel_if_requested(store, task_id, db):
                await _settle_billing(task_id)
                return

            # 按任务归属用户解析其默认文本模型（任务隔离：执行器使用该用户的模型配置）。
            llm = await build_default_text_llm(
                db,
                user_id=task_user_id,
                thinking=True,
            )
            agent = EntityMergerAgent(llm)
            result: EntityMergeResult = agent.extract(
                all_extractions_json=json.dumps(run_args.get("all_shot_extractions") or [], ensure_ascii=False),
                historical_library_json=json.dumps(run_args.get("historical_library") or {}, ensure_ascii=False),
                script_division_json=json.dumps(run_args.get("script_division") or {}, ensure_ascii=False),
                previous_merge_json=json.dumps(run_args.get("previous_merge") or {}, ensure_ascii=False),
                conflict_resolutions_json=json.dumps(run_args.get("conflict_resolutions") or [], ensure_ascii=False),
            )
            await store.set_progress(task_id, 100)
            await store.set_result(task_id, result.model_dump())
            if await _cancel_if_requested(store, task_id, db):
                await _settle_billing(task_id)
                return
            await store.set_status(task_id, TaskStatus.succeeded)
            await db.commit()
            await _settle_billing(task_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("merge task failed: %s", task_id)
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            await store.set_error(task_id, str(exc), error_trace=traceback.format_exc())
            await store.set_status(task_id, TaskStatus.failed)
            await db.commit()
        await _settle_billing(task_id)


async def _settle_billing(task_id: str) -> None:
    """进程内任务（merge/variant，不走 Celery）终态结算积分。

    为什么是 async：merge/variant 通过 `asyncio.create_task` 在**已运行的事件循环**内执行，
    若调用同步桥 `settle_task_billing_sync`（内部 `asyncio.run`）会抛
    `RuntimeError: asyncio.run() cannot be called from a running event loop`，导致结算
    静默失败（被 sync 包装的 except 吞掉）→ 冻结积分泄漏，只能等 Task 7 的 Beat 补偿兜底。
    故直接 `await settle_task_billing_async(task_id)`，在同一事件循环内完成结算。

    幂等：`settle_task_billing_async` 对 billing_id=None 与非终态均安全跳过；账本层幂等。
    """
    from app.services.points.billing import settle_task_billing_async

    try:
        await settle_task_billing_async(task_id)
    except Exception:  # noqa: BLE001 - 结算失败不阻断任务流程，Task 7 补偿兜底
        logger.exception("in-process settle failed for task_id=%s", task_id)


def spawn_merge_task(task_id: str) -> None:
    asyncio.create_task(run_merge_task(task_id))
def spawn_consistency_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


async def run_variant_task(task_id: str) -> None:
    async with async_session_maker() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.get(task_id)
        if task is None:
            logger.warning("variant task not found: %s", task_id)
            return

        # 入口取消：任务尚未进入 running，但用户已请求取消 → 标记 cancelled 并结算。
        # 必须结算（解冻）：merge/variant 经 asyncio.create_task 执行，不走 Celery 的
        # finally 钩子，cancel 路由的立即解冻也不适用（非 Celery executor 无法 revoke），
        # 故每个到达 cancelled 终态的分支都要显式 `await _settle_billing(task_id)`，否则冻结积分泄漏。
        if await _cancel_if_requested(store, task_id, db):
            await _settle_billing(task_id)
            return

        await store.set_status(task_id, TaskStatus.running)
        await store.set_progress(task_id, 5)
        await db.commit()
        run_args = task.payload.get("run_args") or {}
        task_user_id = task.user_id

    try:
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            # try 起点取消：已 running、尚未调用 LLM → 同样必须结算。
            if await _cancel_if_requested(store, task_id, db):
                await _settle_billing(task_id)
                return

            # 按任务归属用户解析其默认文本模型（任务隔离）。
            llm = await build_default_text_llm(
                db,
                user_id=task_user_id,
                thinking=True,
            )
            agent = VariantAnalyzerAgent(llm)
            result: VariantAnalysisResult = agent.extract(
                merged_library_json=json.dumps(run_args.get("merged_library") or {}, ensure_ascii=False),
                all_extractions_json=json.dumps(run_args.get("all_shot_extractions") or [], ensure_ascii=False),
                script_division_json=json.dumps(run_args.get("script_division") or {}, ensure_ascii=False),
            )
            await store.set_progress(task_id, 100)
            await store.set_result(task_id, result.model_dump())
            if await _cancel_if_requested(store, task_id, db):
                await _settle_billing(task_id)
                return
            await store.set_status(task_id, TaskStatus.succeeded)
            await db.commit()
            await _settle_billing(task_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("variant task failed: %s", task_id)
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            await store.set_error(task_id, str(exc), error_trace=traceback.format_exc())
            await store.set_status(task_id, TaskStatus.failed)
            await db.commit()
        await _settle_billing(task_id)


def spawn_variant_task(task_id: str) -> None:
    asyncio.create_task(run_variant_task(task_id))
def spawn_character_portrait_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


def spawn_prop_info_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


def spawn_scene_info_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


def spawn_costume_info_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)
def spawn_script_optimization_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


def spawn_script_simplification_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)
