"""分镜准备页聚合状态服务。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import Character, ShotCharacterLink
from app.schemas.studio.cast import ShotCharacterLinkCreate
from app.schemas.studio.shots import ProjectAssetLinkCreate
from app.schemas.studio.shots import (
    ActionBeatPhaseRead,
    ShotDialogLineRead,
    ShotExtractedDialogueCandidateRead,
    ShotPreparationLinkEntityType,
    ShotPreparationStateRead,
)
from app.services.studio.shot_assets import create_project_asset_link, delete_project_asset_link_by_entity
from app.services.studio.action_beats import infer_action_beat_sequence
from app.services.studio.shot_details import get as get_shot_detail
from app.services.studio.shot_character_links import list_by_shot as list_shot_character_links, upsert as upsert_shot_character_link
from app.services.studio.shot_assets_overview import get_shot_assets_overview
from app.services.studio.shot_dialogs import list_by_shot as list_saved_dialog_lines_by_shot
from app.services.studio.shot_extracted_candidates import (
    mark_all_linked_ignored_for_entity,
    mark_ignored,
    mark_ignored_by_name,
)
from app.services.studio.shot_extracted_dialogue_candidates import list_by_shot as list_dialogue_candidates_by_shot
from app.services.studio.shots import build_shot_read, get as get_shot


async def build_shot_preparation_state(
    db: AsyncSession,
    *,
    shot_id: str,
) -> ShotPreparationStateRead:
    """组装分镜准备页所需的统一聚合状态。"""
    shot = await get_shot(db, shot_id=shot_id)
    shot_read = await build_shot_read(db, shot=shot)
    detail = await get_shot_detail(db, shot_id=shot_id)
    assets_overview = await get_shot_assets_overview(db, shot_id=shot_id)
    dialogue_candidates = [
        ShotExtractedDialogueCandidateRead.model_validate(row)
        for row in await list_dialogue_candidates_by_shot(db, shot_id=shot_id)
    ]
    saved_dialogue_lines = [
        ShotDialogLineRead.model_validate(row)
        for row in await list_saved_dialog_lines_by_shot(db, shot_id=shot_id)
    ]
    pending_confirm_count = (
        int(assets_overview.summary.pending_count or 0)
        + int(shot_read.extraction.pending_dialogue_count or 0)
    )
    basic_info_ready = bool((shot_read.title or "").strip()) and bool((shot_read.script_excerpt or "").strip())
    semantic_defaults_ready = bool(detail.camera_shot) and bool(detail.angle) and bool(detail.movement) and int(detail.duration or 0) > 0
    action_beats_count = len([item for item in (detail.action_beats or []) if (item or "").strip()])
    action_beats_ready = action_beats_count > 0
    action_beat_phases = [
        ActionBeatPhaseRead(text=item.text, phase=item.phase)
        for item in infer_action_beat_sequence(detail.action_beats)
    ]
    ready_for_generation = (
        shot_read.status.value == "ready"
        and basic_info_ready
        and semantic_defaults_ready
        and action_beats_ready
    )
    return ShotPreparationStateRead(
        shot=shot_read,
        assets_overview=assets_overview,
        dialogue_candidates=dialogue_candidates,
        saved_dialogue_lines=saved_dialogue_lines,
        pending_confirm_count=pending_confirm_count,
        basic_info_ready=basic_info_ready,
        semantic_defaults_ready=semantic_defaults_ready,
        action_beats_ready=action_beats_ready,
        action_beats_count=action_beats_count,
        action_beat_phases=action_beat_phases,
        ready_for_generation=ready_for_generation,
    )


async def link_existing_asset_for_preparation(
    db: AsyncSession,
    *,
    project_id: str,
    chapter_id: str,
    shot_id: str,
    entity_type: ShotPreparationLinkEntityType | str,
    linked_entity_id: str,
) -> ShotPreparationStateRead:
    """在准备页内关联现有实体，并返回最新准备态。"""
    entity_type_value = (
        entity_type
        if isinstance(entity_type, ShotPreparationLinkEntityType)
        else ShotPreparationLinkEntityType(entity_type)
    )
    if entity_type_value == ShotPreparationLinkEntityType.character:
        links = await list_shot_character_links(db, shot_id=shot_id)
        max_index = max((int(link.index or 0) for link in links), default=-1)
        # 追加语义：即使 index 因竞态/可见性算重了，也只顺延而不删除已关联的其它角色
        await upsert_shot_character_link(
            db,
            body=ShotCharacterLinkCreate(
                shot_id=shot_id,
                character_id=linked_entity_id,
                index=max_index + 1,
            ),
            reassign_index_on_conflict=True,
        )
    else:
        await create_project_asset_link(
            db,
            entity_type=entity_type_value.value,
            body=ProjectAssetLinkCreate(
                project_id=project_id,
                chapter_id=chapter_id,
                shot_id=shot_id,
                asset_id=linked_entity_id,
            ),
        )
    return await build_shot_preparation_state(db, shot_id=shot_id)


async def unlink_asset_for_preparation(
    db: AsyncSession,
    *,
    shot_id: str,
    entity_type: ShotPreparationLinkEntityType | str,
    entity_id: str,
    candidate_id: int | None = None,
) -> ShotPreparationStateRead:
    """在准备页内解除已关联实体，并返回最新准备态。

    支持 character / scene / prop / costume 四种类型。
    传入 candidate_id 时按主键精确忽略目标候选；若多个候选指向同一实体，
    仅在没有其他 linked 候选仍引用该实体时才删除 ProjectPropLink，
    避免连带误删其他正常关联的卡片。
    """
    entity_type_value = (
        entity_type
        if isinstance(entity_type, ShotPreparationLinkEntityType)
        else ShotPreparationLinkEntityType(entity_type)
    )
    if entity_type_value == ShotPreparationLinkEntityType.character:
        stmt = select(ShotCharacterLink).where(
            ShotCharacterLink.shot_id == shot_id,
            ShotCharacterLink.character_id == entity_id,
        )
        old_link = (await db.execute(stmt)).scalars().one_or_none()
        if old_link is not None:
            await db.execute(
                delete(ShotCharacterLink).where(ShotCharacterLink.id == old_link.id)
            )
        # 查找角色名并将对应候选标记为 ignored，避免卡片回退到"待确认"区
        character = await db.get(Character, entity_id)
        if character is not None and character.name:
            await mark_ignored_by_name(
                db, shot_id=shot_id, candidate_type="character", candidate_name=str(character.name)
            )
    else:
        candidate_type_str_map: dict[ShotPreparationLinkEntityType, str] = {
            ShotPreparationLinkEntityType.scene: "scene",
            ShotPreparationLinkEntityType.prop: "prop",
            ShotPreparationLinkEntityType.costume: "costume",
        }
        candidate_type_str = candidate_type_str_map.get(entity_type_value)

        # Step 1: 精确忽略被点击的候选（按 ID）
        if candidate_id is not None:
            try:
                await mark_ignored(db, candidate_id=candidate_id)
            except (ValueError, Exception):
                pass

        # Step 2: 级联忽略同镜头内其他所有 linked 到该实体的候选
        # overview 已将多候选合并为一张卡片，忽略该卡片即意味着忽略全部关联候选
        if candidate_type_str:
            await mark_all_linked_ignored_for_entity(
                db,
                shot_id=shot_id,
                candidate_type=candidate_type_str,
                entity_id=entity_id,
            )

        # Step 3: 所有候选均已忽略，安全删除 ProjectPropLink
        await delete_project_asset_link_by_entity(
            db,
            entity_type=entity_type_value.value,
            shot_id=shot_id,
            entity_id=entity_id,
            revert_candidate=False,
        )

    return await build_shot_preparation_state(db, shot_id=shot_id)


async def replace_asset_for_preparation(
    db: AsyncSession,
    *,
    project_id: str,
    chapter_id: str,
    shot_id: str,
    entity_type: ShotPreparationLinkEntityType | str,
    old_entity_id: str,
    new_entity_id: str,
) -> ShotPreparationStateRead:
    """在准备页内替换已关联实体：先移除旧关联，再建立新关联，返回最新准备态。

    支持 character / scene / prop / costume 四种类型。
    """
    entity_type_value = (
        entity_type
        if isinstance(entity_type, ShotPreparationLinkEntityType)
        else ShotPreparationLinkEntityType(entity_type)
    )
    if entity_type_value == ShotPreparationLinkEntityType.character:
        # 删除旧角色关联（按 shot_id + character_id 查找）
        stmt = select(ShotCharacterLink).where(
            ShotCharacterLink.shot_id == shot_id,
            ShotCharacterLink.character_id == old_entity_id,
        )
        old_link = (await db.execute(stmt)).scalars().one_or_none()
        old_index: int | None = None
        if old_link is not None:
            old_index = int(old_link.index or 0)
            await db.execute(
                delete(ShotCharacterLink).where(ShotCharacterLink.id == old_link.id)
            )
        # 级联忽略旧角色的候选：与 scene/prop/costume 分支保持一致，
        # 避免候选仍以 'linked' 状态出现在 overview 中
        await mark_all_linked_ignored_for_entity(
            db,
            shot_id=shot_id,
            candidate_type="character",
            entity_id=old_entity_id,
        )
        if old_index is not None:
            # 有实际 ShotCharacterLink：旧 index 已释放，复用该槽位（重排语义）
            await upsert_shot_character_link(
                db,
                body=ShotCharacterLinkCreate(
                    shot_id=shot_id,
                    character_id=new_entity_id,
                    index=old_index,
                ),
            )
        else:
            # 旧角色仅通过候选 linked_entity_id 显示为"已关联"，无实际 ShotCharacterLink；
            # 追加语义插入，避免以 index=0 踢走其他已关联角色导致它们退回"新提取"
            existing_links = await list_shot_character_links(db, shot_id=shot_id)
            safe_index = max((int(link.index or 0) for link in existing_links), default=-1) + 1
            await upsert_shot_character_link(
                db,
                body=ShotCharacterLinkCreate(
                    shot_id=shot_id,
                    character_id=new_entity_id,
                    index=safe_index,
                ),
                reassign_index_on_conflict=True,
            )
    else:
        # 删除旧资产关联：不回退候选为 pending，而是级联标记为 ignored
        # 替换操作表达"不再需要旧资产"，旧候选不应重新出现在待确认区
        await delete_project_asset_link_by_entity(
            db,
            entity_type=entity_type_value.value,
            shot_id=shot_id,
            entity_id=old_entity_id,
            revert_candidate=False,
        )
        candidate_type_str_map: dict[ShotPreparationLinkEntityType, str] = {
            ShotPreparationLinkEntityType.scene: "scene",
            ShotPreparationLinkEntityType.prop: "prop",
            ShotPreparationLinkEntityType.costume: "costume",
        }
        candidate_type_str = candidate_type_str_map.get(entity_type_value)
        if candidate_type_str:
            await mark_all_linked_ignored_for_entity(
                db,
                shot_id=shot_id,
                candidate_type=candidate_type_str,
                entity_id=old_entity_id,
            )
        await create_project_asset_link(
            db,
            entity_type=entity_type_value.value,
            body=ProjectAssetLinkCreate(
                project_id=project_id,
                chapter_id=chapter_id,
                shot_id=shot_id,
                asset_id=new_entity_id,
            ),
        )
    return await build_shot_preparation_state(db, shot_id=shot_id)
