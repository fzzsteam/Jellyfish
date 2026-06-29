"""镜头角色关联服务：封装阵容查询与 upsert 规则。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import Character, Chapter, Project, ProjectCharacterLink, Shot, ShotCharacterLink
from app.schemas.studio.cast import ShotCharacterLinkCreate
from app.services.common import create_and_refresh, entity_not_found, flush_and_refresh, require_entity
from app.services.studio.shot_extracted_candidates import mark_linked_by_name, mark_pending_by_name


async def _load_shot_project(db: AsyncSession, *, shot_id: str) -> Project:
    """根据镜头定位项目，用于角色资产的用户归属校验。"""

    stmt = (
        select(Project)
        .join(Chapter, Chapter.project_id == Project.id)
        .join(Shot, Shot.chapter_id == Chapter.id)
        .where(Shot.id == shot_id)
    )
    project = (await db.execute(stmt)).scalars().one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Shot"))
    return project


async def _load_character_for_project(
    db: AsyncSession,
    *,
    character_id: str,
    project: Project,
) -> Character:
    """只允许当前项目用户拥有的角色资产被关联到项目分镜。"""

    character = await db.get(Character, character_id)
    if character is None or character.user_id != project.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=entity_not_found("Character"))
    return character


async def _ensure_project_character_link(
    db: AsyncSession,
    *,
    project_id: str,
    character_id: str,
) -> None:
    """幂等写入项目级角色关联，让用户资产库角色进入当前项目角色库。"""

    existing = (
        await db.execute(
            select(ProjectCharacterLink).where(
                ProjectCharacterLink.project_id == project_id,
                ProjectCharacterLink.chapter_id.is_(None),
                ProjectCharacterLink.shot_id.is_(None),
                ProjectCharacterLink.character_id == character_id,
            )
        )
    ).scalars().one_or_none()
    if existing is not None:
        return
    db.add(ProjectCharacterLink(project_id=project_id, character_id=character_id))
    await db.flush()


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
    project = await _load_shot_project(db, shot_id=body.shot_id)
    # 角色是用户级资产：分镜可关联当前项目用户资产库中的角色，并会补齐项目级角色关联。
    character = await _load_character_for_project(db, character_id=body.character_id, project=project)

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
        await _ensure_project_character_link(db, project_id=project.id, character_id=body.character_id)
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
    await _ensure_project_character_link(db, project_id=project.id, character_id=body.character_id)
    await mark_linked_by_name(
        db,
        shot_id=body.shot_id,
        candidate_type="character",
        candidate_name=character.name,
        linked_entity_id=body.character_id,
    )
    return row
