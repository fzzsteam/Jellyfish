"""镜头自动准备服务：在分镜提取后批量关联资产并接受对白候选。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.studio import (
    Actor,
    ActorImage,
    Character,
    CharacterImage,
    Costume,
    CostumeImage,
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
from app.services.studio.shot_status import recompute_shot_status_sync


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


def auto_prepare_chapter_shots_sync(
    db: Session,
    *,
    project_id: str,
    chapter_id: str,
) -> AutoPreparationSummary:
    """批量自动准备章节镜头的资产与对白候选。

    该服务只自动确认有高置信唯一匹配且已有 file_id 图片的资产；其余候选保留为
    pending，让用户在分镜编辑页补图、修正或新建资产。
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
    for candidate in candidates:
        if candidate.candidate_status != ShotCandidateStatus.pending:
            continue
        candidate_type = ShotCandidateType(str(candidate.candidate_type))
        match = _pick_unique_match(
            str(candidate.candidate_name),
            options_by_type.get(candidate_type, []),
        )
        if match is None:
            summary.pending_asset_count += 1
            continue
        _link_candidate(
            db,
            project_id=project_id,
            chapter_id=chapter_id,
            candidate=candidate,
            option=match,
        )
        summary.linked_asset_count += 1

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
