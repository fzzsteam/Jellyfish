"""给 Celery worker 使用的同步任务执行服务。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid as _uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.chains.agents import ElementExtractorAgent, ScriptDividerAgent
from app.chains.agents import (
    CharacterPortraitAnalysisAgent,
    ConsistencyCheckerAgent,
    CostumeInfoAnalysisAgent,
    PropInfoAnalysisAgent,
    SceneInfoAnalysisAgent,
    ScriptOptimizerAgent,
    ScriptSimplifierAgent,
)
from app.chains.agents.script_processing_agents import (
    ScriptConsistencyCheckResult,
    ScriptDivisionResult,
    ScriptOptimizationResult,
    ScriptSimplificationResult,
)
from app.core.db_sync import sync_session_maker
from app.models.studio import Chapter
from app.services.script_extraction_cache import (
    build_script_extract_cache_key,
    get_cached_script_extract,
    set_cached_script_extract,
)
from app.services.llm.runtime import build_default_text_llm_sync
from app.services.studio.script_division import write_division_result_to_chapter_sync
from app.services.studio.shot_extracted_candidates import (
    sync_from_extraction_draft_sync as sync_shot_extracted_candidates_from_draft_sync,
)
from app.services.studio.shot_extracted_dialogue_candidates import (
    sync_from_extraction_draft_sync as sync_shot_extracted_dialogue_candidates_from_draft_sync,
)
from app.services.studio.shot_auto_preparation import AutoPreparationSummary, auto_prepare_chapter_shots_sync
from app.services.studio.shot_semantic_defaults import apply_shot_semantic_defaults_from_draft_sync
from app.services.worker.task_executor import (
    AbstractLLMResultGenerator,
    AbstractWorkerTaskExecutor,
    WorkerTaskContext,
)


logger = logging.getLogger(__name__)


class DivideResultGenerator(AbstractLLMResultGenerator):
    thinking = False

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> ScriptDivisionResult:
        agent = ScriptDividerAgent(llm)
        return agent.divide_script(script_text=str(run_args.get("script_text") or ""))


class ExtractResultGenerator(AbstractLLMResultGenerator):
    thinking = False

    def generate(self, db: Session, run_args: dict[str, Any], *, user_id: str) -> tuple[Any, bool]:
        return generate_extraction_result(
            db=db,
            user_id=user_id,
            project_id=str(run_args.get("project_id") or ""),
            chapter_id=str(run_args.get("chapter_id") or ""),
            script_text=str(run_args.get("script_text") or ""),
            script_division=dict(run_args.get("script_division") or {}),
            consistency=dict(run_args.get("consistency") or {}) if run_args.get("consistency") else None,
            refresh_cache=bool(run_args.get("refresh_cache")),
        )

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> Any:  # pragma: no cover - 不直接走这里
        raise NotImplementedError


class ConsistencyResultGenerator(AbstractLLMResultGenerator):
    thinking = True

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> ScriptConsistencyCheckResult:
        agent = ConsistencyCheckerAgent(llm)
        return agent.extract(script_text=str(run_args.get("script_text") or ""))


class CharacterPortraitResultGenerator(AbstractLLMResultGenerator):
    thinking = True

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> Any:
        agent = CharacterPortraitAnalysisAgent(llm)
        return agent.analyze_character_description(
            character_context=run_args.get("character_context"),
            character_description=str(run_args.get("character_description") or ""),
        )


class PropInfoResultGenerator(AbstractLLMResultGenerator):
    thinking = True

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> Any:
        agent = PropInfoAnalysisAgent(llm)
        return agent.analyze_prop_description(
            prop_context=run_args.get("prop_context"),
            prop_description=str(run_args.get("prop_description") or ""),
        )


class SceneInfoResultGenerator(AbstractLLMResultGenerator):
    thinking = True

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> Any:
        agent = SceneInfoAnalysisAgent(llm)
        return agent.analyze_scene_description(
            scene_context=run_args.get("scene_context"),
            scene_description=str(run_args.get("scene_description") or ""),
        )


class CostumeInfoResultGenerator(AbstractLLMResultGenerator):
    thinking = True

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> Any:
        agent = CostumeInfoAnalysisAgent(llm)
        return agent.analyze_costume_description(
            costume_context=run_args.get("costume_context"),
            costume_description=str(run_args.get("costume_description") or ""),
        )


class ScriptOptimizationResultGenerator(AbstractLLMResultGenerator):
    thinking = True

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> ScriptOptimizationResult:
        agent = ScriptOptimizerAgent(llm)
        return agent.extract(
            script_text=str(run_args.get("script_text") or ""),
            consistency_json=json.dumps(dict(run_args.get("consistency") or {}), ensure_ascii=False),
        )


class ScriptSimplificationResultGenerator(AbstractLLMResultGenerator):
    thinking = True

    def generate_with_llm(self, llm, run_args: dict[str, Any]) -> ScriptSimplificationResult:
        agent = ScriptSimplifierAgent(llm)
        return agent.extract(script_text=str(run_args.get("script_text") or ""))


class DivideTaskExecutor(AbstractWorkerTaskExecutor):
    task_kind = "script_divide"
    timeout_seconds = 1800.0

    def __init__(self) -> None:
        super().__init__(session_maker=sync_session_maker)
        self._generator = DivideResultGenerator()
        self._pending_image_task_ids: list[str] = []

    def execute(self, ctx: WorkerTaskContext, run_args: dict[str, Any]) -> ScriptDivisionResult:
        return self._generator.generate(ctx.db, run_args, user_id=ctx.task.user_id)

    def should_apply(self, ctx: WorkerTaskContext, run_args: dict[str, Any], result: ScriptDivisionResult) -> bool:  # noqa: ARG002
        return bool(run_args.get("write_to_db"))

    def apply_result(self, ctx: WorkerTaskContext, run_args: dict[str, Any], result: ScriptDivisionResult) -> None:
        chapter_id = str(run_args.get("chapter_id") or "")
        if not chapter_id:
            raise HTTPException(status_code=400, detail="chapter_id is required for write_to_db=true")
        apply_division_result(ctx.db, chapter_id=chapter_id, result=result)
        script_text = str(run_args.get("script_text") or "")
        summary = apply_auto_extraction_after_division(
            ctx.db, user_id=ctx.task.user_id, chapter_id=chapter_id, result=result,
            script_text=script_text,
            cascade_root_billing_id=ctx.task.billing_id,
        )
        self._pending_image_task_ids = summary.image_task_ids if summary is not None else []

    def after_apply_commit(self, task_id: str, run_args: dict[str, Any], result: Any) -> None:
        from app.tasks.execute_task import enqueue_task_execution  # 避免循环导入
        for image_task_id in self._pending_image_task_ids:
            try:
                enqueue_task_execution(image_task_id)
            except Exception:  # noqa: BLE001
                logger.warning("auto_prep: 图片任务入队失败 task_id=%s", image_task_id)
        self._pending_image_task_ids = []


class ExtractTaskExecutor(AbstractWorkerTaskExecutor):
    task_kind = "script_extract"
    timeout_seconds = 1800.0

    def __init__(self) -> None:
        super().__init__(session_maker=sync_session_maker)
        self._generator = ExtractResultGenerator()
        self._pending_image_task_ids: list[str] = []

    def execute(self, ctx: WorkerTaskContext, run_args: dict[str, Any]) -> tuple[Any, bool]:
        return self._generator.generate(ctx.db, run_args, user_id=ctx.task.user_id)

    def serialize_result(self, result: tuple[Any, bool]) -> dict[str, Any]:
        draft, from_cache = result
        return {
            "draft": draft.model_dump(),
            "from_cache": from_cache,
        }

    def should_apply(self, ctx: WorkerTaskContext, run_args: dict[str, Any], result: tuple[Any, bool]) -> bool:  # noqa: ARG002
        return True

    def apply_result(self, ctx: WorkerTaskContext, run_args: dict[str, Any], result: tuple[Any, bool]) -> None:
        draft, _from_cache = result
        chapter_id = str(run_args.get("chapter_id") or "")
        apply_extraction_result(ctx.db, chapter_id=chapter_id, draft=draft)
        project_id = str(run_args.get("project_id") or "")
        if project_id and chapter_id:
            summary = auto_prepare_chapter_shots_sync(
                ctx.db, user_id=ctx.task.user_id, project_id=project_id, chapter_id=chapter_id,
                cascade_root_billing_id=ctx.task.billing_id,
            )
            self._pending_image_task_ids = summary.image_task_ids

    def after_apply_commit(self, task_id: str, run_args: dict[str, Any], result: Any) -> None:
        from app.tasks.execute_task import enqueue_task_execution  # 避免循环导入
        for image_task_id in self._pending_image_task_ids:
            try:
                enqueue_task_execution(image_task_id)
            except Exception:  # noqa: BLE001
                logger.warning("auto_prep: 图片任务入队失败 task_id=%s", image_task_id)
        self._pending_image_task_ids = []


class ConsistencyTaskExecutor(AbstractWorkerTaskExecutor):
    task_kind = "script_consistency"
    succeeded_progress = 100
    timeout_seconds = 900.0

    def __init__(self) -> None:
        super().__init__(session_maker=sync_session_maker)
        self._generator = ConsistencyResultGenerator()

    def execute(self, ctx: WorkerTaskContext, run_args: dict[str, Any]) -> ScriptConsistencyCheckResult:
        return self._generator.generate(ctx.db, run_args, user_id=ctx.task.user_id)


class _SimpleLLMTaskExecutor(AbstractWorkerTaskExecutor):
    succeeded_progress = 100
    timeout_seconds = 900.0
    generator_class: type[AbstractLLMResultGenerator]

    def __init__(self) -> None:
        super().__init__(session_maker=sync_session_maker)
        self._generator = self.generator_class()

    def execute(self, ctx: WorkerTaskContext, run_args: dict[str, Any]) -> Any:
        return self._generator.generate(ctx.db, run_args, user_id=ctx.task.user_id)


class CharacterPortraitTaskExecutor(_SimpleLLMTaskExecutor):
    task_kind = "script_character_portrait"
    generator_class = CharacterPortraitResultGenerator


class PropInfoTaskExecutor(_SimpleLLMTaskExecutor):
    task_kind = "script_prop_info"
    generator_class = PropInfoResultGenerator


class SceneInfoTaskExecutor(_SimpleLLMTaskExecutor):
    task_kind = "script_scene_info"
    generator_class = SceneInfoResultGenerator


class CostumeInfoTaskExecutor(_SimpleLLMTaskExecutor):
    task_kind = "script_costume_info"
    generator_class = CostumeInfoResultGenerator


class ScriptOptimizationTaskExecutor(_SimpleLLMTaskExecutor):
    task_kind = "script_optimize"
    generator_class = ScriptOptimizationResultGenerator


class ScriptSimplificationTaskExecutor(_SimpleLLMTaskExecutor):
    task_kind = "script_simplify"
    generator_class = ScriptSimplificationResultGenerator


def generate_division_result(
    *,
    db: Session,
    user_id: str,
    script_text: str,
) -> ScriptDivisionResult:
    llm = build_default_text_llm_sync(db, user_id=user_id, thinking=False)
    agent = ScriptDividerAgent(llm)
    return agent.divide_script(script_text=script_text)


def apply_division_result(
    db: Session,
    *,
    chapter_id: str,
    result: ScriptDivisionResult,
) -> None:
    write_division_result_to_chapter_sync(db, chapter_id=chapter_id, result=result)


def generate_extraction_result(
    *,
    db: Session,
    user_id: str,
    project_id: str,
    chapter_id: str,
    script_text: str = "",
    script_division: dict[str, Any],
    consistency: dict[str, Any] | None,
    refresh_cache: bool,
) -> tuple[Any, bool]:
    resolved_script_text = _resolve_extraction_script_text(
        db,
        chapter_id=chapter_id,
        script_text=script_text,
        script_division=script_division,
    )
    cache_key = build_script_extract_cache_key(
        project_id=project_id,
        chapter_id=chapter_id,
        script_text=resolved_script_text,
        script_division=script_division,
        consistency=consistency,
    )

    result = None
    from_cache = False
    if not refresh_cache:
        cached_result = get_cached_script_extract(cache_key)
        if cached_result is not None:
            if _draft_has_extractable_candidates(cached_result):
                result = cached_result
                from_cache = True
            else:
                logger.warning(
                    "script_extract: 忽略空缓存草稿并重新提取 chapter_id=%s",
                    chapter_id,
                )

    if result is None:
        llm = build_default_text_llm_sync(db, user_id=user_id, thinking=False)
        agent = ElementExtractorAgent(llm)
        extract_kwargs = dict(
            project_id=project_id,
            chapter_id=chapter_id,
            script_text=resolved_script_text,
            script_division_json=json.dumps(script_division, ensure_ascii=False),
            consistency_json=json.dumps(consistency or {}, ensure_ascii=False),
        )
        result = agent.extract(**extract_kwargs)
        # deepseek 系模型偶发会在这类长上下文结构化抽取里"跑偏"：把整段原文
        # 原样复读进一个 schema 没要求的字段，而 characters/scenes/props/shots
        # 全部留空——不是解析失败（pydantic 校验通过），是这次生成本身没做抽取
        # 工作。实测同样的输入换一次调用大概率能拿到正常结果，所以这里做一次
        # 有界重试（只重试一次，不无限重试），把这种模型抖动对用户屏蔽掉，而不是
        # 直接静默丢弃整份候选、让"一键分镜拆分"看似成功实则没有任何资产。
        if not _draft_has_extractable_candidates(result):
            logger.warning(
                "script_extract: 首次提取草稿为空，重试一次 chapter_id=%s script_text_len=%d",
                chapter_id,
                len(resolved_script_text),
            )
            result = agent.extract(**extract_kwargs)

        if _draft_has_extractable_candidates(result):
            set_cached_script_extract(cache_key, result)
        else:
            # 记录草稿的整体形状而非仅一句"为空"：区分"LLM 连 shots 骨架都没输出"
            # （通常是这次调用本身出了问题，如超时重试后拿到降级/截断响应）与
            # "shots 骨架在、但没识别出任何角色/场景/道具"（更像模型对这段原文
            # 真判断没有可提取实体）。没有这层信息时，排查空草稿只能靠离线重放
            # 复现整条链路，成本很高。
            shots = list(getattr(result, "shots", []) or [])
            logger.warning(
                "script_extract: 重试后草稿仍为空，不写入缓存 chapter_id=%s "
                "script_text_len=%d shots_len=%d characters=%d scenes=%d props=%d costumes=%d",
                chapter_id,
                len(resolved_script_text),
                len(shots),
                len(getattr(result, "characters", []) or []),
                len(getattr(result, "scenes", []) or []),
                len(getattr(result, "props", []) or []),
                len(getattr(result, "costumes", []) or []),
            )

    return result, from_cache


def _resolve_extraction_script_text(
    db: Session,
    *,
    chapter_id: str,
    script_text: str,
    script_division: dict[str, Any],
) -> str:
    """为信息提取恢复章节全文，避免自动准备只拿分镜摘要导致资产/对白候选为空。

    一键分镜与异步刷新候选来自不同入口；历史任务或旧前端可能没有在
    run_args 中携带 ``script_text``。这里优先使用调用方传入的文本，其次从
    Chapter.condensed_text/raw_text 兜底，最后再拼接分镜摘录，确保 LLM 至少能看到
    可提取的上下文。
    """

    text = (script_text or "").strip()
    if text:
        return text

    if chapter_id:
        chapter = db.get(Chapter, chapter_id)
        if chapter is not None:
            chapter_text = (chapter.condensed_text or chapter.raw_text or "").strip()
            if chapter_text:
                return chapter_text

    excerpts: list[str] = []
    for shot in list((script_division or {}).get("shots") or []):
        if not isinstance(shot, dict):
            continue
        excerpt = str(shot.get("script_excerpt") or "").strip()
        if excerpt:
            excerpts.append(excerpt)
    return "\n".join(excerpts)


def apply_extraction_result(
    db: Session,
    *,
    chapter_id: str,
    draft: Any,
) -> None:
    """将提取草稿同步为候选与镜头语言默认值。"""

    sync_shot_extracted_candidates_from_draft_sync(db, chapter_id=chapter_id, draft=draft)
    sync_shot_extracted_dialogue_candidates_from_draft_sync(db, chapter_id=chapter_id, draft=draft)
    apply_shot_semantic_defaults_from_draft_sync(db, chapter_id=chapter_id, draft=draft)


def _draft_has_extractable_candidates(draft: Any) -> bool:
    """判断提取草稿是否真的包含可落库的资产或对白候选。

    自动分镜后的二次提取如果返回整章空结果，通常表示模型输出格式漂移或提取失败。
    此时不应调用候选同步逻辑，否则每个镜头会被写入 last_extracted_at 并显示为“已提取无结果”。
    """

    for shot in list(getattr(draft, "shots", []) or []):
        if str(getattr(shot, "scene_name", "") or "").strip():
            return True
        for attr in ("character_names", "prop_names", "costume_names", "dialogue_lines"):
            if list(getattr(shot, attr, []) or []):
                return True
    return False


def apply_auto_extraction_after_division(
    db: Session,
    *,
    user_id: str,
    chapter_id: str,
    result: ScriptDivisionResult,
    script_text: str = "",
    cascade_root_billing_id: str | None = None,
) -> AutoPreparationSummary:
    """在分镜拆分写库后，串行提取每个镜头的资产/对白并执行自动准备。返回自动准备摘要。

    计费契约（修复 auto-extract 漏费）：
    - auto-extract 会触发一次文本 LLM 调用（``ElementExtractorAgent.extract``），可能命中缓存
      也可能真正调用模型。此处按用户默认文本模型单价**乐观冻结**一笔积分：
      - 缓存命中（``from_cache=True``）→ LLM 未被调用 → **解冻**（用户免费）。
      - 缓存未命中（``from_cache=False``）→ LLM 已调用 → **消费**冻结积分。
    - 余额不足 → 跳过 auto-extraction（记 warning），divide 主流程不受影响，后续 auto-prep
      仍正常执行（图片级联各自独立冻结）。
    - 冻结/解冻/消费通过 ``asyncio.run`` 桥接异步账本（与 ``settle_task_billing_sync`` 同款），
      DivideTaskExecutor 在 Celery worker 同步上下文运行，无运行中的事件循环，``asyncio.run`` 安全。
    """
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # 解析默认文本模型单价，用于乐观冻结。模型未配置时 text_model=None：仍尝试提取
    # （可能命中缓存，此时无需计费；缓存未命中则提取会在 LLM 构建处抛 503，与历史行为一致）。
    text_model = None
    try:
        from app.services.llm.runtime import _require_provider_and_model_sync
        from app.models.llm import ModelCategoryKey
        _provider, text_model = _require_provider_and_model_sync(
            db,
            user_id=user_id,
            category=ModelCategoryKey.text,
        )
    except Exception:  # noqa: BLE001 - 无默认文本模型：跳过计费但保留提取（缓存可能命中）
        logger.debug(
            "auto_extract: 未配置默认文本模型，跳过计费 chapter_id=%s", chapter_id
        )

    billing_id: str | None = None
    if text_model is not None:
        from app.services.points import InsufficientPointsError, calculate_points
        required = calculate_points(
            category="text",
            unit_points=int(text_model.unit_points),
            duration_seconds=None,
            resolution=None,
            generation_count=1,
        )
        billing_id = _uuid.uuid4().hex

        # 1. 乐观冻结（缓存命中后续解冻，缓存未命中后续消费）。
        try:
            asyncio.run(_freeze_text_call_async(
                user_id=user_id,
                billing_id=billing_id,
                amount=required,
                model_id=str(text_model.id),
                unit_points=int(text_model.unit_points),
                cascade_group_id=cascade_root_billing_id,
            ))
        except InsufficientPointsError as e:
            logger.warning(
                "auto_extract: 余额不足，跳过自动提取 chapter_id=%s available=%s required=%s shortfall=%s",
                chapter_id, e.available, e.required, e.shortfall,
            )
            return auto_prepare_chapter_shots_sync(
                db, user_id=user_id, project_id=chapter.project_id, chapter_id=chapter_id,
                cascade_root_billing_id=cascade_root_billing_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "auto_extract: 文本积分冻结失败，跳过自动提取 chapter_id=%s", chapter_id
            )
            return auto_prepare_chapter_shots_sync(
                db, user_id=user_id, project_id=chapter.project_id, chapter_id=chapter_id,
                cascade_root_billing_id=cascade_root_billing_id,
            )

    # 2. 执行提取（可能缓存命中也可能真正调用 LLM）。
    try:
        draft, from_cache = generate_extraction_result(
            db=db,
            user_id=user_id,
            project_id=chapter.project_id,
            chapter_id=chapter_id,
            script_text=script_text,
            script_division=result.model_dump(),
            consistency=None,
            refresh_cache=False,
        )
    except BaseException:
        # 提取异常 → 若已冻结则解冻，避免悬挂；再上抛让 divide 的 apply_result 链路感知。
        if billing_id is not None:
            try:
                asyncio.run(_unfreeze_text_call_async(user_id=user_id, billing_id=billing_id))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "auto_extract: 解冻失败 billing_id=%s；补偿任务(Task 7)将兜底", billing_id
                )
        raise

    # 3. 按 cache 结果结算：命中 → 解冻（免费），未命中 → 消费（扣减）。仅在已冻结时结算。
    if billing_id is not None:
        try:
            if from_cache:
                asyncio.run(_unfreeze_text_call_async(user_id=user_id, billing_id=billing_id))
            else:
                asyncio.run(_consume_text_call_async(user_id=user_id, billing_id=billing_id))
        except Exception:  # noqa: BLE001
            # 结算失败（mutex race / 锁繁忙等）不阻断提取结果落库；补偿任务(Task 7)兜底。
            logger.exception(
                "auto_extract: 结算失败 billing_id=%s from_cache=%s；补偿任务(Task 7)将兜底",
                billing_id, from_cache,
            )

    if _draft_has_extractable_candidates(draft):
        apply_extraction_result(db, chapter_id=chapter_id, draft=draft)
    else:
        logger.warning(
            "auto_extract: 提取草稿为空，跳过候选同步，避免误标记已提取 chapter_id=%s",
            chapter_id,
        )
    return auto_prepare_chapter_shots_sync(
        db, user_id=user_id, project_id=chapter.project_id, chapter_id=chapter_id,
        cascade_root_billing_id=cascade_root_billing_id,
    )


# ---------------------------------------------------------------------------
# 同步 → 异步账本桥接（auto-extract 在 Celery worker 同步上下文运行）
# 与 billing.settle_task_billing_sync / shot_auto_preparation._run_async 同款模式：
# 开一个独立 async_session_maker 会话调用账本，账本内部自行 COMMIT。
# ---------------------------------------------------------------------------


async def _freeze_text_call_async(
    *,
    user_id: str,
    billing_id: str,
    amount: int,
    model_id: str,
    unit_points: int,
    cascade_group_id: str | None = None,
) -> None:
    """异步冻结一笔文本提取积分。抛 InsufficientPointsError 给调用方决策。"""
    from app.core.db import async_session_maker
    from app.services.points import freeze_points

    async with async_session_maker() as async_db:
        await freeze_points(
            async_db,
            user_id=user_id,
            billing_id=billing_id,
            amount=amount,
            model_id=model_id,
            business_type="script_extract",
            business_id=None,
            cascade_group_id=cascade_group_id,
            snapshot={
                "category": "text",
                "unit_points": unit_points,
                "generation_count": 1,
                "source": "auto_extract",
            },
            created_by=user_id,
        )


async def _consume_text_call_async(*, user_id: str, billing_id: str) -> None:
    """异步消费冻结（缓存未命中、LLM 已调用）。BillingStateError 视为良性竞争吞掉。"""
    from app.core.db import async_session_maker
    from app.services.points import BillingStateError, consume_frozen

    async with async_session_maker() as async_db:
        try:
            await consume_frozen(async_db, user_id=user_id, billing_id=billing_id, created_by="system")
        except BillingStateError:
            logger.warning(
                "auto_extract: consume benign race for billing_id=%s", billing_id
            )


async def _unfreeze_text_call_async(*, user_id: str, billing_id: str) -> None:
    """异步解冻冻结（缓存命中或提取异常）。BillingStateError 视为良性竞争吞掉。"""
    from app.core.db import async_session_maker
    from app.services.points import BillingStateError, unfreeze_frozen

    async with async_session_maker() as async_db:
        try:
            await unfreeze_frozen(
                async_db,
                user_id=user_id,
                billing_id=billing_id,
                remark="auto_extract cache hit or extraction error",
                created_by="system",
            )
        except BillingStateError:
            logger.warning(
                "auto_extract: unfreeze benign race for billing_id=%s", billing_id
            )


def run_divide_task_sync(task_id: str) -> None:
    DivideTaskExecutor().run(task_id)


def run_extract_task_sync(task_id: str) -> None:
    ExtractTaskExecutor().run(task_id)


def run_consistency_task_sync(task_id: str) -> None:
    ConsistencyTaskExecutor().run(task_id)


def run_character_portrait_task_sync(task_id: str) -> None:
    CharacterPortraitTaskExecutor().run(task_id)


def run_prop_info_task_sync(task_id: str) -> None:
    PropInfoTaskExecutor().run(task_id)


def run_scene_info_task_sync(task_id: str) -> None:
    SceneInfoTaskExecutor().run(task_id)


def run_costume_info_task_sync(task_id: str) -> None:
    CostumeInfoTaskExecutor().run(task_id)


def run_script_optimization_task_sync(task_id: str) -> None:
    ScriptOptimizationTaskExecutor().run(task_id)


def run_script_simplification_task_sync(task_id: str) -> None:
    ScriptSimplificationTaskExecutor().run(task_id)
