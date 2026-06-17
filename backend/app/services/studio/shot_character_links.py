"""镜头角色关联服务：封装阵容查询与 upsert 规则。"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import Character, Shot, ShotCharacterLink
from app.schemas.studio.cast import ShotCharacterLinkCreate
from app.services.common import create_and_refresh, entity_not_found, flush_and_refresh, require_entity
from app.services.studio.shot_extracted_candidates import mark_linked_by_name, mark_pending_by_name


async def list_by_shot(
    db: AsyncSession,
    *,
    shot_id: str,
) -> list[ShotCharacterLink]:
    """按镜头查询角色关联列表。"""
    await require_entity(db, Shot, shot_id, detail=entity_not_found("Shot"))

    stmt = (
        select(ShotCharacterLink)
        .where(ShotCharacterLink.shot_id == shot_id)
        .order_by(ShotCharacterLink.index.asc(), ShotCharacterLink.id.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def upsert(
    db: AsyncSession,
    *,
    body: ShotCharacterLinkCreate,
    reassign_index_on_conflict: bool = False,
) -> ShotCharacterLink:
    """按镜头与角色 upsert 阵容关系，并处理 index 冲突。

    reassign_index_on_conflict 区分两种语义：
    - False（默认，分镜工作室"设置阵容/重排"）：目标 index 被其它角色占用时，
      删除占用者并将其候选退回 pending —— 即"用本角色替换该槽位"。
    - True（分镜准备页"关联新角色"）：目标 index 被占用时，本角色顺延到空闲 index，
      绝不删除/退回其它已关联角色。用于避免并发或 index 计算竞态把先关联的角色
      误删并退回"待确认候选"。
    """
    await require_entity(db, Shot, body.shot_id, detail=entity_not_found("Shot"))
    # 角色为全局共享资产，分镜可关联资产库中任意角色（含其它项目归属的角色），
    # 因此不再强制 character.project_id == chapter.project_id；仅校验角色存在即可。
    character = await require_entity(db, Character, body.character_id, detail=entity_not_found("Character"))

    existing_same_character_stmt = select(ShotCharacterLink).where(
        ShotCharacterLink.shot_id == body.shot_id,
        ShotCharacterLink.character_id == body.character_id,
    )
    existing = (await db.execute(existing_same_character_stmt)).scalars().one_or_none()
    if existing is not None:
        # 追加语义下重复关联同一角色是幂等的：保持其原有位置，避免改 index 引发冲突
        if not reassign_index_on_conflict:
            existing.index = body.index
        existing.note = body.note
        existing = await flush_and_refresh(db, existing)
        await mark_linked_by_name(
            db,
            shot_id=body.shot_id,
            candidate_type="character",
            candidate_name=character.name,
            linked_entity_id=body.character_id,
        )
        return existing

    target_index = body.index
    existing_same_index_stmt = select(ShotCharacterLink).where(
        ShotCharacterLink.shot_id == body.shot_id,
        ShotCharacterLink.index == target_index,
    )
    existing_same_index = (await db.execute(existing_same_index_stmt)).scalars().one_or_none()
    if existing_same_index is not None:
        if reassign_index_on_conflict:
            # 追加语义：顺延到空闲 index，保留占用该槽位的已关联角色
            max_index = await db.scalar(
                select(func.max(ShotCharacterLink.index)).where(ShotCharacterLink.shot_id == body.shot_id)
            )
            target_index = int(max_index or 0) + 1
        else:
            # 重排语义：替换占用该 index 的角色，并将其候选退回 pending
            previous_character = await db.get(Character, existing_same_index.character_id)
            await db.execute(delete(ShotCharacterLink).where(ShotCharacterLink.id == existing_same_index.id))
            if previous_character is not None and getattr(previous_character, "name", None):
                await mark_pending_by_name(
                    db,
                    shot_id=body.shot_id,
                    candidate_type="character",
                    candidate_name=str(previous_character.name),
                )

    row = await create_and_refresh(
        db,
        ShotCharacterLink(
            shot_id=body.shot_id,
            character_id=body.character_id,
            index=target_index,
            note=body.note,
        ),
    )
    await mark_linked_by_name(
        db,
        shot_id=body.shot_id,
        candidate_type="character",
        candidate_name=character.name,
        linked_entity_id=body.character_id,
    )
    return row
