"""镜头资产总览服务：聚合已关联资产与提取候选。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import (
    CharacterImage,
    CostumeImage,
    PropImage,
    SceneImage,
    Shot,
    ShotCandidateStatus,
)
from app.models.task import GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.schemas.studio.shots import (
    ShotAssetOverviewItem,
    ShotAssetsOverviewRead,
    ShotAssetsOverviewSummary,
)
from app.services.common import entity_not_found, require_entity
from app.services.studio.shot_assets import list_shot_linked_assets
from app.services.studio.shot_extracted_candidates import list_by_shot


_ACTIVE_TASK_STATUSES = (GenerationTaskStatus.pending.value, GenerationTaskStatus.running.value)
_PREPARATION_PENDING_TYPES = {"character", "scene", "prop"}


def _counts_as_preparation_pending(item: ShotAssetOverviewItem) -> bool:
    """判断资产总览条目是否应计入分镜准备阶段的待确认数量。

    服装候选只作为参考资产出现在总览里，不阻塞 shot.status ready，也不应让
    分镜详情页出现“待确认关联”但没有可处理卡片的状态。
    """
    return (
        item.type in _PREPARATION_PENDING_TYPES
        and item.candidate_status == ShotCandidateStatus.pending.value
    )


async def _detect_generating_entity_keys(
    db: AsyncSession,
    items: list[ShotAssetOverviewItem],
) -> set[str]:
    """批量检测哪些资产实体当前有活跃（pending/running）的图片生成任务。

    返回形如 '{type}:{entity_id}' 的键集合，供调用方快速判断 is_generating 状态。
    character 类型通过 relation_type='character' 直接匹配 entity_id；
    scene/prop/costume 先查对应图片表的 image_id，再关联 GenerationTaskLink。
    """
    # 只检测已关联但尚无图片的条目（file_id 为空时才可能处于生成中）
    candidates = [
        item for item in items
        if item.is_linked and not item.file_id and item.linked_entity_id
    ]
    if not candidates:
        return set()

    generating: set[str] = set()

    # ---------- character：relation_type='character', relation_entity_id=entity_id ----------
    char_ids = [item.linked_entity_id for item in candidates if item.type == "character"]
    if char_ids:
        stmt = (
            select(GenerationTaskLink.relation_entity_id)
            .join(GenerationTask, GenerationTask.id == GenerationTaskLink.task_id)
            .where(
                GenerationTaskLink.relation_type == "character",
                GenerationTaskLink.relation_entity_id.in_(char_ids),
                GenerationTask.status.in_(_ACTIVE_TASK_STATUSES),
            )
        )
        for eid in (await db.execute(stmt)).scalars().all():
            generating.add(f"character:{eid}")

    # ---------- 辅助：按 entity_id 批量查活跃 image 任务 ----------
    async def _check_image_type(
        entity_type: str,
        image_model: type,
        parent_field: str,
        relation_type_str: str,
        entity_ids: list[str],
    ) -> None:
        if not entity_ids:
            return
        # step 1: 查出所有 image_id → entity_id 映射
        image_rows = (
            await db.execute(
                select(image_model.id, getattr(image_model, parent_field))  # type: ignore[attr-defined]
                .where(getattr(image_model, parent_field).in_(entity_ids))  # type: ignore[attr-defined]
            )
        ).all()
        if not image_rows:
            return
        image_id_to_entity = {str(row[0]): str(row[1]) for row in image_rows}
        # step 2: 查哪些 image_id 有活跃任务
        active_rows = (
            await db.execute(
                select(GenerationTaskLink.relation_entity_id)
                .join(GenerationTask, GenerationTask.id == GenerationTaskLink.task_id)
                .where(
                    GenerationTaskLink.relation_type == relation_type_str,
                    GenerationTaskLink.relation_entity_id.in_(list(image_id_to_entity.keys())),
                    GenerationTask.status.in_(_ACTIVE_TASK_STATUSES),
                )
            )
        ).scalars().all()
        for image_id_str in active_rows:
            entity_id = image_id_to_entity.get(image_id_str)
            if entity_id:
                generating.add(f"{entity_type}:{entity_id}")

    scene_ids = [item.linked_entity_id for item in candidates if item.type == "scene"]
    prop_ids = [item.linked_entity_id for item in candidates if item.type == "prop"]
    costume_ids = [item.linked_entity_id for item in candidates if item.type == "costume"]

    await _check_image_type("scene", SceneImage, "scene_id", "scene_image", scene_ids)
    await _check_image_type("prop", PropImage, "prop_id", "prop_image", prop_ids)
    await _check_image_type("costume", CostumeImage, "costume_id", "costume_image", costume_ids)

    return generating


def _normalize_name(name: str) -> str:
    return str(name).strip()


def _payload_value(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _enum_or_str_value(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    if raw is None:
        return None
    return str(raw)


def _overview_candidate_status(candidate_status: str | None, *, is_linked: bool) -> str | None:
    """归一化总览展示状态，避免真实关联仍被 pending 候选卡住。

    资产新建页可能先建立真实镜头关联，再通过刷新回到准备页；此时同名或同实体
    的提取候选仍可能保持 pending。总览应以真实关联为准，否则 UI 会同时显示
    “已关联图片”和“仍需确认”的矛盾状态。
    """
    if is_linked and candidate_status == ShotCandidateStatus.pending.value:
        return ShotCandidateStatus.linked.value
    return candidate_status


async def get_shot_assets_overview(
    db: AsyncSession,
    *,
    shot_id: str,
) -> ShotAssetsOverviewRead:
    shot = await require_entity(db, Shot, shot_id, detail=entity_not_found("Shot"), status_code=400)
    linked_assets = await list_shot_linked_assets(db, shot_id=shot_id)
    candidates = await list_by_shot(db, shot_id=shot_id)

    item_by_key: dict[str, ShotAssetOverviewItem] = {}

    for linked in linked_assets:
        key = f"{linked.type}:{_normalize_name(linked.name)}"
        item_by_key[key] = ShotAssetOverviewItem(
            key=key,
            type=linked.type,
            name=linked.name,
            description=None,
            thumbnail=(linked.thumbnail or None),
            file_id=linked.file_id,
            source="linked",
            candidate_id=None,
            candidate_status=None,
            linked_entity_id=linked.id,
            linked_image_id=linked.image_id,
            is_linked=True,
        )

    for candidate in candidates:
        candidate_type = _enum_or_str_value(candidate.candidate_type)
        candidate_status = _enum_or_str_value(candidate.candidate_status)
        if not candidate_type:
            continue
        key = f"{candidate_type}:{_normalize_name(candidate.candidate_name)}"
        payload = dict(candidate.payload or {})
        existing = item_by_key.get(key)
        description = _payload_value(payload, "description")
        thumbnail = _payload_value(payload, "thumbnail")
        file_id = _payload_value(payload, "file_id")

        if existing is None:
            item_by_key[key] = ShotAssetOverviewItem(
                key=key,
                type=candidate_type,  # type: ignore[arg-type]
                name=candidate.candidate_name,
                description=description,
                thumbnail=thumbnail,
                file_id=file_id,
                source="candidate",
                candidate_id=candidate.id,
                candidate_status=candidate_status,  # type: ignore[arg-type]
                linked_entity_id=candidate.linked_entity_id,
                linked_image_id=None,
                is_linked=candidate_status == ShotCandidateStatus.linked.value,
            )
            continue

        item_by_key[key] = existing.model_copy(
            update={
                "description": description or existing.description,
                "thumbnail": thumbnail or existing.thumbnail,
                "file_id": file_id or existing.file_id,
                "source": "both",
                "candidate_id": candidate.id,
                "candidate_status": _overview_candidate_status(candidate_status, is_linked=True),
                "linked_entity_id": existing.linked_entity_id or candidate.linked_entity_id,
                "is_linked": True,
            }
        )

    # 去重：多个候选指向同一实体时，合并为一张卡片
    # 优先保留有图片的条目；显示名取脚本提取的候选名（与实体名不同时），而非实体名
    # 例："荔枝"候选 + "青荔枝"候选均关联到"荔枝"实体 → 显示"青荔枝"并附"荔枝"图片
    _entity_to_keys: dict[str, list[str]] = {}
    for _k, _item in list(item_by_key.items()):
        if _item.linked_entity_id:
            _entity_to_keys.setdefault(
                f"{_item.type}:{_item.linked_entity_id}", []
            ).append(_k)

    for _dup_keys in _entity_to_keys.values():
        if len(_dup_keys) <= 1:
            continue
        _dup_items = [item_by_key[k] for k in _dup_keys if k in item_by_key]
        if len(_dup_items) <= 1:
            continue

        # 主条目：有实际图片数据的优先（来自 linked_assets）
        _primary = next(
            (i for i in _dup_items if i.file_id or i.thumbnail),
            _dup_items[0],
        )
        # 备选名：名称与实体名不同的候选项（脚本原文更具体）
        _alt = next(
            (
                i for i in _dup_items
                if i.name != _primary.name and i.source in ("candidate", "both")
            ),
            None,
        )

        for _k in _dup_keys:
            item_by_key.pop(_k, None)

        if _alt is not None:
            _merged = _primary.model_copy(update={
                "name": _alt.name,
                "key": f"{_primary.type}:{_normalize_name(_alt.name)}",
                "candidate_id": _alt.candidate_id,
                "candidate_status": _overview_candidate_status(_alt.candidate_status, is_linked=_primary.is_linked),
            })
        else:
            _merged = _primary

        item_by_key[_merged.key] = _merged

    items_unsorted = list(item_by_key.values())

    # 标记正在生成中的资产（已关联但图片尚未落库且有活跃任务）
    generating_keys = await _detect_generating_entity_keys(db, items_unsorted)
    if generating_keys:
        items_unsorted = [
            item.model_copy(update={"is_generating": True})
            if f"{item.type}:{item.linked_entity_id}" in generating_keys
            else item
            for item in items_unsorted
        ]

    items = sorted(
        items_unsorted,
        key=lambda item: (
            0
            if item.candidate_status == ShotCandidateStatus.pending.value
            else 1
            if item.is_linked
            else 2,
            item.type,
            item.name,
        ),
    )

    linked_count = sum(1 for item in items if item.is_linked)
    pending_count = sum(1 for item in items if _counts_as_preparation_pending(item))
    ignored_count = sum(1 for item in items if item.candidate_status == ShotCandidateStatus.ignored.value)

    return ShotAssetsOverviewRead(
        shot_id=shot.id,
        skip_extraction=bool(shot.skip_extraction),
        status=shot.status,
        summary=ShotAssetsOverviewSummary(
            linked_count=linked_count,
            pending_count=pending_count,
            ignored_count=ignored_count,
            total_count=len(items),
        ),
        items=items,
    )
