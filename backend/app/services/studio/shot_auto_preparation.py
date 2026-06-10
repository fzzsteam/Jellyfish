"""镜头自动准备服务：在分镜提取后批量关联资产并接受对白候选。"""

from __future__ import annotations

import logging
import uuid as _uuid_mod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.models.studio import (
    Actor,
    ActorImage,
    AssetViewAngle,
    Character,
    CharacterImage,
    Costume,
    CostumeImage,
    Project,
    ProjectActorLink,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    Prop,
    PropImage,
    Scene,
    SceneImage,
    Shot,
    ShotCandidateStatus,
    ShotCandidateType,
    ShotCharacterLink,
    ShotDetail,
    ShotDialogLine,
    ShotDialogueCandidateStatus,
    ShotExtractedCandidate,
    ShotExtractedDialogueCandidate,
    ShotStatus,
)
from app.models.task import GenerationDeliveryMode, GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.models.types import ProjectStyle, ProjectVisualStyle
from app.services.llm.provider_resolver import resolve_provider_config_from_provider
from app.services.studio.shot_status import recompute_shot_status_sync

_logger = logging.getLogger(__name__)


FUZZY_MATCH_THRESHOLD = 0.92
FUZZY_AMBIGUITY_GAP = 0.08
_CHINESE_MODIFIER_CHARS = set("青绿绿色红赤朱白黑玄金银黄蓝紫粉灰棕褐瓷陶木竹铜铁石玉")
_CHINESE_SUFFIX_CHARS = set("子儿")


@dataclass(slots=True)
class AutoPreparationSummary:
    """记录自动准备批处理结果，用于测试、日志和后续诊断。"""

    shot_count: int = 0
    linked_asset_count: int = 0
    pending_asset_count: int = 0
    accepted_dialogue_count: int = 0
    skipped_dialogue_count: int = 0
    ready_shot_count: int = 0
    pending_shot_count: int = 0
    auto_created_asset_count: int = 0
    image_task_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _AssetOption:
    """内部资产匹配项，统一不同资产类型的名称、ID 与可用图片状态。"""

    entity_id: str
    name: str
    has_image: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_name(value: str) -> str:
    """归一化中英文资产名，降低空白、标点与大小写差异对匹配的影响。"""

    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _normalize_core_name(value: str) -> str:
    """移除常见中文颜色、材质修饰和弱后缀，用于保守近似匹配。"""

    normalized = _normalize_name(value)
    for weak_word in ("演员", "角色", "人物"):
        normalized = normalized.replace(weak_word, "")
    core = "".join(ch for ch in normalized if ch not in _CHINESE_MODIFIER_CHARS)
    while len(core) > 1 and core[-1] in _CHINESE_SUFFIX_CHARS:
        core = core[:-1]
    return core or normalized


def _is_subsequence(shorter: str, longer: str) -> bool:
    """判断较短名称是否按顺序完整出现在较长名称中。"""

    if not shorter:
        return False
    cursor = 0
    for ch in longer:
        if cursor < len(shorter) and shorter[cursor] == ch:
            cursor += 1
    return cursor == len(shorter)


def _similarity(left: str, right: str) -> float:
    """计算两个归一化名称的保守相似度。"""

    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def _rank_name_match(candidate_name: str, option_name: str) -> tuple[int, float]:
    """返回候选名与资产名的匹配等级与分数，等级越高越可信。"""

    normalized_candidate = _normalize_name(candidate_name)
    normalized_option = _normalize_name(option_name)
    if not normalized_candidate or not normalized_option:
        return (0, 0.0)
    if normalized_candidate == normalized_option:
        return (3, 1.0)

    candidate_core = _normalize_core_name(candidate_name)
    option_core = _normalize_core_name(option_name)
    if candidate_core and option_core and candidate_core == option_core:
        return (2, 1.0)
    if candidate_core and option_core and len(candidate_core) > len(option_core) >= 2:
        if _is_subsequence(option_core, candidate_core):
            return (2, len(option_core) / len(candidate_core))
    if len(normalized_candidate) > len(normalized_option) >= 2:
        if _is_subsequence(normalized_option, normalized_candidate):
            return (2, len(normalized_option) / len(normalized_candidate))

    return (1, _similarity(normalized_candidate, normalized_option))


def _pick_unique_match(candidate_name: str, options: list[_AssetOption]) -> _AssetOption | None:
    """只返回同类型、高置信且唯一的资产匹配，避免自动误关联。"""

    scored = sorted(
        (
            (*_rank_name_match(candidate_name, option.name), option)
            for option in options
            if option.has_image
        ),
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )
    if not scored:
        return None
    top_rank, top_score, top_option = scored[0]
    if top_rank == 0:
        return None
    if top_rank == 1 and top_score < FUZZY_MATCH_THRESHOLD:
        return None
    if len(scored) > 1:
        second_rank, second_score, _ = scored[1]
        if top_rank == 2 and second_rank == 2:
            return None
        if second_rank == top_rank and top_score - second_score < FUZZY_AMBIGUITY_GAP:
            return None
    return top_option


def _load_asset_options(db: Session, *, project_id: str) -> dict[ShotCandidateType, list[_AssetOption]]:
    """加载每种候选类型的可匹配资产，并标记是否已有可用 file_id 图片。"""

    character_rows = db.execute(
        select(Character.id, Character.name, func.count(CharacterImage.id))
        .join(CharacterImage, CharacterImage.character_id == Character.id)
        .where(Character.project_id == project_id, CharacterImage.file_id.is_not(None))
        .group_by(Character.id, Character.name)
    ).all()
    scene_rows = db.execute(
        select(Scene.id, Scene.name, func.count(SceneImage.id))
        .join(SceneImage, SceneImage.scene_id == Scene.id)
        .where(SceneImage.file_id.is_not(None))
        .group_by(Scene.id, Scene.name)
    ).all()
    prop_rows = db.execute(
        select(Prop.id, Prop.name, func.count(PropImage.id))
        .join(PropImage, PropImage.prop_id == Prop.id)
        .where(PropImage.file_id.is_not(None))
        .group_by(Prop.id, Prop.name)
    ).all()
    costume_rows = db.execute(
        select(Costume.id, Costume.name, func.count(CostumeImage.id))
        .join(CostumeImage, CostumeImage.costume_id == Costume.id)
        .where(CostumeImage.file_id.is_not(None))
        .group_by(Costume.id, Costume.name)
    ).all()
    return {
        ShotCandidateType.character: [
            _AssetOption(entity_id=str(row[0]), name=str(row[1]), has_image=bool(row[2]))
            for row in character_rows
        ],
        ShotCandidateType.scene: [
            _AssetOption(entity_id=str(row[0]), name=str(row[1]), has_image=bool(row[2]))
            for row in scene_rows
        ],
        ShotCandidateType.prop: [
            _AssetOption(entity_id=str(row[0]), name=str(row[1]), has_image=bool(row[2]))
            for row in prop_rows
        ],
        ShotCandidateType.costume: [
            _AssetOption(entity_id=str(row[0]), name=str(row[1]), has_image=bool(row[2]))
            for row in costume_rows
        ],
    }


def _load_actor_options(db: Session) -> list[_AssetOption]:
    """加载已有可用图片的演员资产，用于角色候选自动关联演员。"""

    actor_rows = db.execute(
        select(Actor.id, Actor.name, func.count(ActorImage.id))
        .join(ActorImage, ActorImage.actor_id == Actor.id)
        .where(ActorImage.file_id.is_not(None))
        .group_by(Actor.id, Actor.name)
    ).all()
    return [
        _AssetOption(entity_id=str(row[0]), name=str(row[1]), has_image=bool(row[2]))
        for row in actor_rows
    ]


def _next_character_index(db: Session, *, shot_id: str) -> int:
    """为镜头角色关联选择下一个不冲突的排序号。"""

    max_index = db.scalar(select(func.max(ShotCharacterLink.index)).where(ShotCharacterLink.shot_id == shot_id))
    return int(max_index or 0) + 1


def _ensure_character_link(db: Session, *, shot_id: str, character_id: str) -> None:
    """幂等写入镜头与角色的关联。"""

    existing = db.scalar(
        select(ShotCharacterLink).where(
            ShotCharacterLink.shot_id == shot_id,
            ShotCharacterLink.character_id == character_id,
        )
    )
    if existing is not None:
        return
    db.add(
        ShotCharacterLink(
            shot_id=shot_id,
            character_id=character_id,
            index=_next_character_index(db, shot_id=shot_id),
        )
    )


def _ensure_project_actor_link(db: Session, *, project_id: str, actor_id: str) -> None:
    """幂等写入项目级演员关联，供角色自动匹配演员后在项目演员页展示。"""

    existing = db.scalar(
        select(ProjectActorLink).where(
            ProjectActorLink.project_id == project_id,
            ProjectActorLink.chapter_id.is_(None),
            ProjectActorLink.shot_id.is_(None),
            ProjectActorLink.actor_id == actor_id,
        )
    )
    if existing is not None:
        return
    db.add(ProjectActorLink(project_id=project_id, actor_id=actor_id))


def _ensure_character_actor_link(
    db: Session,
    *,
    project_id: str,
    character_id: str,
    actor_option: _AssetOption | None,
) -> None:
    """当存在唯一演员匹配时，将角色挂到演员并确保项目演员关联存在。"""

    if actor_option is None:
        return
    character = db.get(Character, character_id)
    if character is None:
        return
    if character.actor_id is None:
        character.actor_id = actor_option.entity_id
    if character.actor_id == actor_option.entity_id:
        _ensure_project_actor_link(db, project_id=project_id, actor_id=actor_option.entity_id)


def _ensure_project_asset_link(
    db: Session,
    *,
    project_id: str,
    chapter_id: str,
    shot_id: str,
    candidate_type: ShotCandidateType,
    entity_id: str,
) -> None:
    """幂等写入场景、道具、服装的项目/章节/镜头级资产关联。"""

    link_config = {
        ShotCandidateType.scene: (ProjectSceneLink, ProjectSceneLink.scene_id, "scene_id"),
        ShotCandidateType.prop: (ProjectPropLink, ProjectPropLink.prop_id, "prop_id"),
        ShotCandidateType.costume: (ProjectCostumeLink, ProjectCostumeLink.costume_id, "costume_id"),
    }
    model, id_column, id_key = link_config[candidate_type]
    existing = db.scalar(
        select(model).where(
            model.project_id == project_id,
            model.chapter_id == chapter_id,
            model.shot_id == shot_id,
            id_column == entity_id,
        )
    )
    if existing is not None:
        return
    db.add(
        model(
            project_id=project_id,
            chapter_id=chapter_id,
            shot_id=shot_id,
            **{id_key: entity_id},
        )
    )
    # session 配置了 autoflush=False，立即 flush 让本次 add 对后续 SELECT 可见，
    # 避免同一 shot 多个 candidate 匹配同一资产时出现重复 add 导致唯一约束冲突。
    db.flush()


def _link_candidate(
    db: Session,
    *,
    project_id: str,
    chapter_id: str,
    candidate: ShotExtractedCandidate,
    option: _AssetOption,
) -> None:
    """将单个资产候选写入真实关联，并把候选标记为 linked。"""

    candidate_type = ShotCandidateType(str(candidate.candidate_type))
    if candidate_type == ShotCandidateType.character:
        _ensure_character_link(db, shot_id=candidate.shot_id, character_id=option.entity_id)
        _ensure_character_actor_link(
            db,
            project_id=project_id,
            character_id=option.entity_id,
            actor_option=_pick_unique_match(str(candidate.candidate_name), _load_actor_options(db)),
        )
    else:
        _ensure_project_asset_link(
            db,
            project_id=project_id,
            chapter_id=chapter_id,
            shot_id=candidate.shot_id,
            candidate_type=candidate_type,
            entity_id=option.entity_id,
        )
    candidate.candidate_status = ShotCandidateStatus.linked
    candidate.linked_entity_id = option.entity_id
    candidate.confirmed_at = _utc_now()


def _resolve_dialog_index_sync(db: Session, *, shot_id: str, preferred_index: int) -> int:
    """为自动接受的对白选择不冲突的行号。"""

    existing = db.scalar(
        select(ShotDialogLine.id).where(
            ShotDialogLine.shot_detail_id == shot_id,
            ShotDialogLine.index == preferred_index,
        )
    )
    if existing is None:
        return preferred_index
    max_index = db.scalar(select(func.max(ShotDialogLine.index)).where(ShotDialogLine.shot_detail_id == shot_id))
    return int(max_index or 0) + 1


def _find_existing_dialog_line(
    db: Session,
    *,
    candidate: ShotExtractedDialogueCandidate,
) -> ShotDialogLine | None:
    """按文本、说话人和目标查找已存在对白行，保证重复执行不会复制台词。"""

    return db.scalar(
        select(ShotDialogLine).where(
            ShotDialogLine.shot_detail_id == candidate.shot_id,
            ShotDialogLine.text == candidate.text,
            ShotDialogLine.speaker_name == candidate.speaker_name,
            ShotDialogLine.target_name == candidate.target_name,
        )
    )


def _accept_dialogue_candidate(db: Session, *, candidate: ShotExtractedDialogueCandidate) -> bool:
    """自动接受单条对白候选，并复用已存在的对白行。"""

    if candidate.candidate_status == ShotDialogueCandidateStatus.accepted and candidate.linked_dialog_line_id:
        return False
    detail = db.get(ShotDetail, candidate.shot_id)
    if detail is None:
        return False

    line = _find_existing_dialog_line(db, candidate=candidate)
    if line is None:
        line = ShotDialogLine(
            shot_detail_id=candidate.shot_id,
            index=_resolve_dialog_index_sync(
                db,
                shot_id=candidate.shot_id,
                preferred_index=int(candidate.index or 0),
            ),
            text=candidate.text,
            line_mode=candidate.line_mode,
            speaker_name=candidate.speaker_name,
            target_name=candidate.target_name,
        )
        db.add(line)
        db.flush()

    candidate.candidate_status = ShotDialogueCandidateStatus.accepted
    candidate.linked_dialog_line_id = line.id
    candidate.confirmed_at = _utc_now()
    return True


def _find_entity_by_name_sync(
    db: Session,
    *,
    candidate_type: ShotCandidateType,
    candidate_name: str,
    project_id: str,
) -> str | None:
    """按归一化名称精确匹配现有资产实体，返回 entity_id 或 None。"""
    norm = _normalize_name(candidate_name)
    if not norm:
        return None

    if candidate_type == ShotCandidateType.character:
        rows = db.execute(select(Character.id, Character.name).where(Character.project_id == project_id)).all()
    elif candidate_type == ShotCandidateType.scene:
        rows = db.execute(select(Scene.id, Scene.name)).all()
    elif candidate_type == ShotCandidateType.prop:
        rows = db.execute(select(Prop.id, Prop.name)).all()
    elif candidate_type == ShotCandidateType.costume:
        rows = db.execute(select(Costume.id, Costume.name)).all()
    else:
        return None

    for row_id, row_name in rows:
        if _normalize_name(str(row_name)) == norm:
            return str(row_id)
    return None


def _ngram_overlap(shorter: str, longer: str, min_gram: int = 2) -> bool:
    """判断 shorter 的任意 min_gram+ 字连续子串是否出现在 longer 中。

    用于捕捉如 "青荔枝" 与 "青绿色硬荔枝" 共享 "荔枝" 这类关键标识符的情况，
    核心名剥离修饰词后仍存在共同语义锚点，但原始子串检测会因两侧修饰词不同而漏判。
    """
    for gram_len in range(min_gram, len(shorter) + 1):
        for i in range(len(shorter) - gram_len + 1):
            if shorter[i : i + gram_len] in longer:
                return True
    return False


def _has_name_overlap_with_existing(candidate_name: str, existing_names: list[str]) -> bool:
    """检查候选名是否与任意已有实体名存在子串或核心子串关系。

    用于二次轮自动建档前的保守歧义检测：若候选名包含在某个现有名称里，
    或现有名称被包含在候选名里（含核心名版本），则认为可能是对现有资产的
    缩写引用，不应擅自创建新实体。

    额外使用 n-gram 检测：取两名称中较短者的所有 2+ 字连续子串，若任意一个
    出现在另一名称中则视为重叠（分别在归一化全名和核心名两个层次各做一次）。
    """
    norm_cand = _normalize_name(candidate_name)
    core_cand = _normalize_core_name(candidate_name)
    if not norm_cand or len(norm_cand) < 2:
        return False
    for name in existing_names:
        norm_opt = _normalize_name(name)
        core_opt = _normalize_core_name(name)
        if not norm_opt:
            continue
        # 全名双向子串检测
        if len(norm_cand) >= 2 and (norm_cand in norm_opt or norm_opt in norm_cand):
            return True
        # 核心名双向子串检测
        if core_cand and core_opt and len(core_cand) >= 2 and len(core_opt) >= 2:
            if core_cand in core_opt or core_opt in core_cand:
                return True
        # N-gram 检测：取较短一方的所有 2+ 字连续子串，检查是否出现在较长一方中
        # 捕捉 "青荔枝"/"青绿色硬荔枝" 这类修饰词不同但语义锚字相同的情况
        if len(norm_cand) >= 2 and len(norm_opt) >= 2:
            shorter_n, longer_n = (norm_cand, norm_opt) if len(norm_cand) <= len(norm_opt) else (norm_opt, norm_cand)
            if _ngram_overlap(shorter_n, longer_n):
                return True
        if core_cand and core_opt and len(core_cand) >= 2 and len(core_opt) >= 2:
            shorter_c, longer_c = (core_cand, core_opt) if len(core_cand) <= len(core_opt) else (core_opt, core_cand)
            if _ngram_overlap(shorter_c, longer_c):
                return True
    return False


def _create_entity_sync(
    db: Session,
    *,
    candidate_type: ShotCandidateType,
    name: str,
    description: str,
    style: ProjectStyle,
    visual_style: ProjectVisualStyle,
    project_id: str,
) -> str:
    """同步创建资产实体，scene/prop/costume 同时初始化正面视角图片槽位，返回 entity_id。"""
    entity_id = str(_uuid_mod.uuid4())
    if candidate_type == ShotCandidateType.character:
        db.add(Character(id=entity_id, project_id=project_id, name=name, description=description, style=style, visual_style=visual_style))
        db.flush()
    elif candidate_type == ShotCandidateType.scene:
        db.add(Scene(id=entity_id, name=name, description=description, style=style, visual_style=visual_style))
        db.flush()
        db.add(SceneImage(scene_id=entity_id, view_angle=AssetViewAngle.front))
        db.flush()
    elif candidate_type == ShotCandidateType.prop:
        db.add(Prop(id=entity_id, name=name, description=description, style=style, visual_style=visual_style))
        db.flush()
        db.add(PropImage(prop_id=entity_id, view_angle=AssetViewAngle.front))
        db.flush()
    elif candidate_type == ShotCandidateType.costume:
        db.add(Costume(id=entity_id, name=name, description=description, style=style, visual_style=visual_style))
        db.flush()
        db.add(CostumeImage(costume_id=entity_id, view_angle=AssetViewAngle.front))
        db.flush()
    return entity_id


def _get_or_create_image_slot_sync(
    db: Session,
    *,
    candidate_type: ShotCandidateType,
    entity_id: str,
) -> tuple[str, str] | None:
    """获取或创建资产的图片生成槽位，返回 (relation_type, relation_entity_id)。
    character 类型的槽位由 worker 的 _resolve_generated_image_target 负责动态创建。
    """
    if candidate_type == ShotCandidateType.character:
        return ("character", entity_id)

    if candidate_type == ShotCandidateType.scene:
        slot = db.scalar(
            select(SceneImage)
            .where(SceneImage.scene_id == entity_id, SceneImage.file_id.is_(None))
            .order_by(SceneImage.id.asc())
            .limit(1)
        )
        if slot is None:
            slot = SceneImage(scene_id=entity_id, view_angle=AssetViewAngle.front)
            db.add(slot)
            db.flush()
        return ("scene_image", str(slot.id))

    if candidate_type == ShotCandidateType.prop:
        slot = db.scalar(
            select(PropImage)
            .where(PropImage.prop_id == entity_id, PropImage.file_id.is_(None))
            .order_by(PropImage.id.asc())
            .limit(1)
        )
        if slot is None:
            slot = PropImage(prop_id=entity_id, view_angle=AssetViewAngle.front)
            db.add(slot)
            db.flush()
        return ("prop_image", str(slot.id))

    if candidate_type == ShotCandidateType.costume:
        slot = db.scalar(
            select(CostumeImage)
            .where(CostumeImage.costume_id == entity_id, CostumeImage.file_id.is_(None))
            .order_by(CostumeImage.id.asc())
            .limit(1)
        )
        if slot is None:
            slot = CostumeImage(costume_id=entity_id, view_angle=AssetViewAngle.front)
            db.add(slot)
            db.flush()
        return ("costume_image", str(slot.id))

    return None


def _load_image_run_args_sync(
    db: Session,
    *,
    relation_type: str,
    relation_entity_id: str,
    prompt: str,
) -> dict | None:
    """从 DB 加载默认图片模型配置并构建 run_args；未配置时返回 None。"""
    settings = db.get(ModelSettings, 1)
    if settings is None or not settings.default_image_model_id:
        return None
    model = db.get(Model, settings.default_image_model_id)
    if model is None:
        return None
    provider = db.get(Provider, model.provider_id)
    if provider is None:
        return None
    try:
        resolved = resolve_provider_config_from_provider(provider=provider, category=ModelCategoryKey.image)
    except Exception:  # noqa: BLE001
        return None
    return {
        "provider": resolved.provider_key,
        "api_key": resolved.api_key,
        "base_url": resolved.base_url,
        "relation_type": relation_type,
        "relation_entity_id": relation_entity_id,
        "input": {
            "prompt": prompt,
            "model": model.name,
            "purpose": "generic",
        },
    }


def _schedule_image_task_sync(
    db: Session,
    *,
    run_args: dict,
    summary: AutoPreparationSummary,
) -> None:
    """在当前事务的 SAVEPOINT 中创建图片生成任务记录；失败则静默回滚并跳过。"""
    task_id = str(_uuid_mod.uuid4())
    try:
        with db.begin_nested():
            db.add(GenerationTask(
                id=task_id,
                mode=GenerationDeliveryMode.async_polling,
                task_kind="image_generation",
                status=GenerationTaskStatus.pending,
                payload={"run_args": run_args},
            ))
            db.flush()
            db.add(GenerationTaskLink(
                task_id=task_id,
                resource_type="image",
                relation_type=run_args["relation_type"],
                relation_entity_id=run_args["relation_entity_id"],
            ))
            db.flush()
        summary.image_task_ids.append(task_id)
    except Exception:  # noqa: BLE001
        _logger.warning(
            "auto_prep: 图片任务记录创建失败，跳过 relation_type=%s relation_entity_id=%s",
            run_args.get("relation_type"),
            run_args.get("relation_entity_id"),
        )


def _auto_create_and_link_sync(
    db: Session,
    *,
    candidate: ShotExtractedCandidate,
    project_id: str,
    chapter_id: str,
    style: ProjectStyle,
    visual_style: ProjectVisualStyle,
    summary: AutoPreparationSummary,
    batch_pending_names: list[str] | None = None,
) -> bool:
    """为无匹配候选自动创建资产实体、调度图片生成，并完成候选关联。返回是否成功关联。

    batch_pending_names 为同批次中其他仍为 pending 的同类候选名，用于在 DB flush
    前就能检测出批次内名称重叠，避免因处理顺序导致重叠候选被分别新建。
    """
    candidate_type = ShotCandidateType(str(candidate.candidate_type))
    candidate_name = str(candidate.candidate_name)
    description = str((candidate.payload or {}).get("description") or "")
    # 拼接项目视觉风格前缀，让生成图片的风格与项目定位一致
    # 格式示例：「视觉风格：现实、视频风格：真人古装  北宋诗人苏东坡…」
    # 注：SQLAlchemy 加载 ORM 字段时可能返回原始字符串而非枚举实例，
    # 用 getattr(x, 'value', x) 兼容两种情况。
    _vs = getattr(visual_style, "value", visual_style)
    _st = getattr(style, "value", style)
    style_prefix = f"视觉风格：{_vs}、视频风格：{_st}  "
    prompt = style_prefix + (description or candidate_name)

    entity_id = _find_entity_by_name_sync(
        db, candidate_type=candidate_type, candidate_name=candidate_name, project_id=project_id
    )
    if entity_id is None:
        # Before creating a new entity, check if any existing entity has a
        # name-overlap relationship with this candidate (substring in either direction).
        # If so, the candidate is likely an abbreviated reference to an existing entity,
        # not a genuinely new asset — leave it pending for manual resolution.
        if candidate_type == ShotCandidateType.character:
            existing_names = [str(r[0]) for r in db.execute(select(Character.name).where(Character.project_id == project_id)).all()]
        elif candidate_type == ShotCandidateType.scene:
            existing_names = [str(r[0]) for r in db.execute(select(Scene.name)).all()]
        elif candidate_type == ShotCandidateType.prop:
            existing_names = [str(r[0]) for r in db.execute(select(Prop.name)).all()]
        elif candidate_type == ShotCandidateType.costume:
            existing_names = [str(r[0]) for r in db.execute(select(Costume.name)).all()]
        else:
            existing_names = []
        # 同批次内其他仍为 pending 的候选名也纳入重叠检测，避免两个互相重叠的
        # 新候选因处理顺序不同而被分别建档（"青荔枝" 先于 "青绿色硬荔枝" 处理时）
        if batch_pending_names:
            norm_self = _normalize_name(candidate_name)
            existing_names = existing_names + [
                n for n in batch_pending_names if _normalize_name(n) != norm_self
            ]
        if _has_name_overlap_with_existing(candidate_name, existing_names):
            _logger.debug("auto_prep: 候选 '%s' 与现有资产存在名称重叠，保留 pending", candidate_name)
            return False
        try:
            entity_id = _create_entity_sync(
                db,
                candidate_type=candidate_type,
                name=candidate_name,
                description=description,
                style=style,
                visual_style=visual_style,
                project_id=project_id,
            )
            summary.auto_created_asset_count += 1
        except Exception:  # noqa: BLE001
            _logger.warning("auto_prep: 资产创建失败，候选 '%s'(%s) 保留 pending", candidate_name, candidate_type)
            return False

    try:
        slot_info = _get_or_create_image_slot_sync(db, candidate_type=candidate_type, entity_id=entity_id)
        if slot_info is not None:
            relation_type, relation_entity_id = slot_info
            run_args = _load_image_run_args_sync(
                db, relation_type=relation_type, relation_entity_id=relation_entity_id, prompt=prompt
            )
            if run_args is not None:
                _schedule_image_task_sync(db, run_args=run_args, summary=summary)
    except Exception:  # noqa: BLE001
        _logger.warning("auto_prep: 图片生成调度失败，候选 '%s' 仍将完成关联", candidate_name)

    option = _AssetOption(entity_id=entity_id, name=candidate_name, has_image=False)
    _link_candidate(db, project_id=project_id, chapter_id=chapter_id, candidate=candidate, option=option)
    return True


def auto_prepare_chapter_shots_sync(
    db: Session,
    *,
    project_id: str,
    chapter_id: str,
) -> AutoPreparationSummary:
    """批量自动准备章节镜头的资产与对白候选。

    - 第一轮：将有高置信唯一匹配且已有 file_id 图片的候选与现有资产关联。
    - 第二轮：对仍为 pending 的候选，自动创建资产实体并调度图片生成任务；
      创作者只需在资产管理页审核生成结果，无需手动逐一补图。
    - 对白候选全部自动接受。
    """

    summary = AutoPreparationSummary()
    shots = list(db.execute(select(Shot).where(Shot.chapter_id == chapter_id)).scalars().all())
    summary.shot_count = len(shots)
    shot_ids = [shot.id for shot in shots]
    if not shot_ids:
        return summary

    options_by_type = _load_asset_options(db, project_id=project_id)
    candidates = list(
        db.execute(
            select(ShotExtractedCandidate)
            .where(ShotExtractedCandidate.shot_id.in_(shot_ids))
            .order_by(ShotExtractedCandidate.id.asc())
        ).scalars().all()
    )

    # 第一轮：与已有图片的资产高置信匹配
    for candidate in candidates:
        if candidate.candidate_status != ShotCandidateStatus.pending:
            continue
        candidate_type = ShotCandidateType(str(candidate.candidate_type))
        match = _pick_unique_match(
            str(candidate.candidate_name),
            options_by_type.get(candidate_type, []),
        )
        if match is None:
            continue
        _link_candidate(
            db,
            project_id=project_id,
            chapter_id=chapter_id,
            candidate=candidate,
            option=match,
        )
        summary.linked_asset_count += 1

    # 第一轮结束后统一 flush：将所有已写入 session 的 ProjectPropLink / ProjectSceneLink
    # 等关联对象持久化到 DB，保证第二轮的幂等 SELECT 能读到它们。
    # 背景：sync session 配置了 autoflush=False，若不在此显式 flush，第二轮
    # _ensure_project_asset_link 的幂等检查会遗漏 session 中 pending 的对象，
    # 导致同一 (prop/scene/costume, shot) 组合被 db.add 两次，最终在第二轮
    # _create_entity_sync 的 db.flush() 时触发唯一约束冲突。
    db.flush()

    # 第二轮：自动创建资产并调度图片生成（服装不参与自动建档，由创作者手动管理）
    project = db.get(Project, project_id)
    proj_style = project.style if project is not None else ProjectStyle.real_people_city
    proj_visual_style = project.visual_style if project is not None else ProjectVisualStyle.live_action

    # 在第二轮开始前收集所有仍为 pending 的候选名，按类型分组。
    # 传给 _auto_create_and_link_sync 用于批次内重叠检测：防止 "青荔枝" 因早于
    # "青绿色硬荔枝" 处理而错误建档（此时后者尚未 flush 到 DB，DB 查询查不到它）。
    pending_names_by_type: dict[ShotCandidateType, list[str]] = {}
    for _c in candidates:
        if _c.candidate_status == ShotCandidateStatus.pending:
            _ct = ShotCandidateType(str(_c.candidate_type))
            pending_names_by_type.setdefault(_ct, []).append(str(_c.candidate_name))

    for candidate in candidates:
        if candidate.candidate_status != ShotCandidateStatus.pending:
            continue
        # 服装资产款式差异大、需人工审定，跳过自动创建，留给创作者在资产管理页处理
        if ShotCandidateType(str(candidate.candidate_type)) == ShotCandidateType.costume:
            summary.pending_asset_count += 1
            continue
        candidate_type = ShotCandidateType(str(candidate.candidate_type))
        succeeded = _auto_create_and_link_sync(
            db,
            candidate=candidate,
            project_id=project_id,
            chapter_id=chapter_id,
            style=proj_style,
            visual_style=proj_visual_style,
            summary=summary,
            batch_pending_names=pending_names_by_type.get(candidate_type, []),
        )
        if not succeeded:
            summary.pending_asset_count += 1

    dialogue_candidates = list(
        db.execute(
            select(ShotExtractedDialogueCandidate)
            .where(ShotExtractedDialogueCandidate.shot_id.in_(shot_ids))
            .order_by(ShotExtractedDialogueCandidate.id.asc())
        ).scalars().all()
    )
    for candidate in dialogue_candidates:
        if candidate.candidate_status == ShotDialogueCandidateStatus.pending:
            if _accept_dialogue_candidate(db, candidate=candidate):
                summary.accepted_dialogue_count += 1
            else:
                summary.skipped_dialogue_count += 1

    db.flush()
    for shot in shots:
        status = recompute_shot_status_sync(db, shot_id=shot.id)
        if status == ShotStatus.ready:
            summary.ready_shot_count += 1
        else:
            summary.pending_shot_count += 1
    return summary
