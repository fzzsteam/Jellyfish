from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import (
    Chapter,
    Character,
    Project,
    ProjectCharacterLink,
    ProjectStyle,
    ProjectVisualStyle,
    Shot,
    ShotCandidateStatus,
    ShotCandidateType,
    ShotCharacterLink,
    ShotExtractedCandidate,
)
from app.models.user import User
from app.schemas.studio.cast import ShotCharacterLinkCreate
from app.services.studio.shot_character_links import list_by_shot, upsert


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_base_graph(db: AsyncSession) -> None:
    db.add(User(id="test-user", username="test-user", hashed_password="x"))
    db.add(User(id="other-user", username="other-user", hashed_password="x"))
    project = Project(
        id="p1",
        name="项目一",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
        user_id="test-user",
    )
    other_project = Project(
        id="p2",
        name="项目二",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
        user_id="test-user",
    )
    chapter = Chapter(id="c1", project_id="p1", index=1, title="第一章")
    shot = Shot(id="s1", chapter_id="c1", index=1, title="镜头一")
    character_1 = Character(
        id="char1",
        user_id="test-user",
        name="角色一",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    character_2 = Character(
        id="char2",
        user_id="test-user",
        name="角色二",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    foreign_character = Character(
        id="char3",
        user_id="other-user",
        name="其他用户角色",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    db.add_all([project, other_project, chapter, shot, character_1, character_2, foreign_character])
    await db.commit()


@pytest.mark.asyncio
async def test_upsert_rejects_character_from_other_user() -> None:
    """分镜角色关联只能使用当前项目用户名下的角色资产。"""
    db, engine = await _build_session()
    async with db:
        await _seed_base_graph(db)

        with pytest.raises(Exception):
            await upsert(
                db,
                body=ShotCharacterLinkCreate(shot_id="s1", character_id="char3", index=0, note="cross"),
            )

        rows = (await db.execute(select(ShotCharacterLink))).scalars().all()
        assert rows == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_links_user_character_into_project_character_library() -> None:
    """从用户资产库关联角色到分镜时，应同步补齐项目级角色资产关联。"""
    db, engine = await _build_session()
    async with db:
        await _seed_base_graph(db)

        created = await upsert(
            db,
            body=ShotCharacterLinkCreate(shot_id="s1", character_id="char2", index=0, note=""),
        )

        assert created.character_id == "char2"
        project_link = (await db.execute(
            select(ProjectCharacterLink).where(
                ProjectCharacterLink.project_id == "p1",
                ProjectCharacterLink.character_id == "char2",
                ProjectCharacterLink.chapter_id.is_(None),
                ProjectCharacterLink.shot_id.is_(None),
            )
        )).scalars().one_or_none()
        assert project_link is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_updates_existing_same_character_link() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_base_graph(db)

        created = await upsert(
            db,
            body=ShotCharacterLinkCreate(shot_id="s1", character_id="char1", index=0, note="first"),
        )
        updated = await upsert(
            db,
            body=ShotCharacterLinkCreate(shot_id="s1", character_id="char1", index=2, note="updated"),
        )

        rows = (await db.execute(select(ShotCharacterLink))).scalars().all()

        assert created.id == updated.id
        assert updated.index == 2
        assert updated.note == "updated"
        assert len(rows) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_link_existing_two_characters_keeps_both_linked(monkeypatch) -> None:
    """连续关联两个角色：先关联者不应因 index 冲突被删除并退回 pending（复现回归）。"""
    from app.schemas.studio.shots import ShotPreparationLinkEntityType
    from app.services.studio import shot_preparation_state as prep_svc

    async def _fake_build_state(_db, *, shot_id):
        return SimpleNamespace(shot_id=shot_id)

    monkeypatch.setattr(prep_svc, "build_shot_preparation_state", _fake_build_state)

    db, engine = await _build_session()
    async with db:
        await _seed_base_graph(db)
        db.add_all(
            [
                ShotExtractedCandidate(
                    shot_id="s1",
                    candidate_type=ShotCandidateType.character,
                    candidate_name="角色一",
                    candidate_status=ShotCandidateStatus.pending,
                    source="extraction",
                    payload={},
                ),
                ShotExtractedCandidate(
                    shot_id="s1",
                    candidate_type=ShotCandidateType.character,
                    candidate_name="角色二",
                    candidate_status=ShotCandidateStatus.pending,
                    source="extraction",
                    payload={},
                ),
            ]
        )
        await db.flush()

        await prep_svc.link_existing_asset_for_preparation(
            db, project_id="p1", chapter_id="c1", shot_id="s1",
            entity_type=ShotPreparationLinkEntityType.character, linked_entity_id="char1",
        )
        await prep_svc.link_existing_asset_for_preparation(
            db, project_id="p1", chapter_id="c1", shot_id="s1",
            entity_type=ShotPreparationLinkEntityType.character, linked_entity_id="char2",
        )

        listed = await list_by_shot(db, shot_id="s1")
        assert {link.character_id for link in listed} == {"char1", "char2"}
        cand_1 = (await db.execute(
            select(ShotExtractedCandidate).where(ShotExtractedCandidate.candidate_name == "角色一")
        )).scalars().one()
        assert cand_1.candidate_status == ShotCandidateStatus.linked
    await engine.dispose()


@pytest.mark.asyncio
async def test_replace_without_existing_link_does_not_evict_other_characters(monkeypatch) -> None:
    """连续替换角色时，若旧角色没有实际 ShotCharacterLink，不得把其他已关联角色踢出并退回 pending。

    复现场景：
    - char1 已通过 ShotCharacterLink 挂在 index=0。
    - char2 / char3 仅通过候选 candidate_status=linked 显示为"已关联"，无 ShotCharacterLink。
    - 依次"替换" char2 → char_new2、char3 → char_new3。
    - 每次替换不得删除 char1 的 ShotCharacterLink，也不得把 char_new2 退回 pending。
    """
    from app.schemas.studio.shots import ShotPreparationLinkEntityType
    from app.services.studio import shot_preparation_state as prep_svc

    async def _fake_build_state(_db, *, shot_id):
        return SimpleNamespace(shot_id=shot_id)

    monkeypatch.setattr(prep_svc, "build_shot_preparation_state", _fake_build_state)

    db, engine = await _build_session()
    async with db:
        await _seed_base_graph(db)
        # 为新建角色追加补充数据（char4 / char5 用于被替换的目标角色）
        db.add_all(
            [
                Character(
                    id="char4",
                    user_id="test-user",
                    name="角色四",
                    description="",
                    style=ProjectStyle.real_people_city,
                    visual_style=ProjectVisualStyle.live_action,
                ),
                Character(
                    id="char5",
                    user_id="test-user",
                    name="角色五",
                    description="",
                    style=ProjectStyle.real_people_city,
                    visual_style=ProjectVisualStyle.live_action,
                ),
            ]
        )
        # char1 有真实 ShotCharacterLink @0
        db.add(ShotCharacterLink(shot_id="s1", character_id="char1", index=0, note=""))
        # char2 / char3 仅有候选，status=linked，无 ShotCharacterLink
        db.add_all(
            [
                ShotExtractedCandidate(
                    shot_id="s1",
                    candidate_type=ShotCandidateType.character,
                    candidate_name="角色二",
                    candidate_status=ShotCandidateStatus.linked,
                    linked_entity_id="char2",
                    source="extraction",
                    payload={},
                ),
                ShotExtractedCandidate(
                    shot_id="s1",
                    candidate_type=ShotCandidateType.character,
                    candidate_name="角色三",
                    candidate_status=ShotCandidateStatus.linked,
                    linked_entity_id="char3",
                    source="extraction",
                    payload={},
                ),
                ShotExtractedCandidate(
                    shot_id="s1",
                    candidate_type=ShotCandidateType.character,
                    candidate_name="角色一",
                    candidate_status=ShotCandidateStatus.linked,
                    linked_entity_id="char1",
                    source="extraction",
                    payload={},
                ),
            ]
        )
        await db.flush()

        # 第一次替换：char2（无 ShotCharacterLink）→ char4
        await prep_svc.replace_asset_for_preparation(
            db,
            project_id="p1",
            chapter_id="c1",
            shot_id="s1",
            entity_type=ShotPreparationLinkEntityType.character,
            old_entity_id="char2",
            new_entity_id="char4",
        )

        # 第二次替换：char3（无 ShotCharacterLink）→ char5
        await prep_svc.replace_asset_for_preparation(
            db,
            project_id="p1",
            chapter_id="c1",
            shot_id="s1",
            entity_type=ShotPreparationLinkEntityType.character,
            old_entity_id="char3",
            new_entity_id="char5",
        )

        listed = await list_by_shot(db, shot_id="s1")
        char_ids = {link.character_id for link in listed}
        # char1 的 ShotCharacterLink 不应被删除
        assert "char1" in char_ids, f"char1 被意外踢出，当前 links={char_ids}"
        # char4（第一次替换）不应被第二次替换踢出
        assert "char4" in char_ids, f"char4 被第二次替换意外踢出，当前 links={char_ids}"
        # char5 应成功加入
        assert "char5" in char_ids, f"char5 未成功加入，当前 links={char_ids}"

        # char4 对应的候选（角色四）不应退回 pending
        cand_1_status = (await db.execute(
            select(ShotExtractedCandidate.candidate_status)
            .where(ShotExtractedCandidate.shot_id == "s1", ShotExtractedCandidate.candidate_name == "角色一")
        )).scalar_one_or_none()
        assert cand_1_status == ShotCandidateStatus.linked, f"角色一候选被意外退回：{cand_1_status}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_append_mode_keeps_previous_on_index_conflict() -> None:
    """append 模式（reassign_index_on_conflict=True）下，index 冲突应顺延而非踢掉已关联角色。

    复现"关联第二个角色导致第一个退回待确认"的根因：并发/可见性导致两次关联算到同一 index。
    """
    db, engine = await _build_session()
    async with db:
        await _seed_base_graph(db)
        db.add(
            ShotExtractedCandidate(
                shot_id="s1",
                candidate_type=ShotCandidateType.character,
                candidate_name="角色一",
                candidate_status=ShotCandidateStatus.pending,
                source="extraction",
                payload={},
            )
        )
        await db.flush()

        await upsert(db, body=ShotCharacterLinkCreate(shot_id="s1", character_id="char1", index=0, note=""))
        # char2 也算到了 index 0（模拟竞态），append 模式应顺延，不删除 char1
        await upsert(
            db,
            body=ShotCharacterLinkCreate(shot_id="s1", character_id="char2", index=0, note=""),
            reassign_index_on_conflict=True,
        )

        listed = await list_by_shot(db, shot_id="s1")
        by_id = {link.character_id: link.index for link in listed}
        assert set(by_id) == {"char1", "char2"}
        assert by_id["char1"] == 0
        assert by_id["char2"] == 1
        # char1 对应的候选不应被退回 pending
        cand_1 = (await db.execute(
            select(ShotExtractedCandidate).where(ShotExtractedCandidate.candidate_name == "角色一")
        )).scalars().one()
        assert cand_1.candidate_status == ShotCandidateStatus.linked
    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_replaces_existing_same_index_link() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_base_graph(db)

        first = await upsert(
            db,
            body=ShotCharacterLinkCreate(shot_id="s1", character_id="char1", index=1, note="first"),
        )
        second = await upsert(
            db,
            body=ShotCharacterLinkCreate(shot_id="s1", character_id="char2", index=1, note="second"),
        )

        listed = await list_by_shot(db, shot_id="s1")

        assert first.character_id == "char1"
        assert second.character_id == "char2"
        assert len(listed) == 1
        assert listed[0].character_id == "char2"
        assert listed[0].note == "second"
    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_replaces_existing_same_index_link_marks_previous_candidate_back_to_pending() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_base_graph(db)
        candidate_1 = ShotExtractedCandidate(
            shot_id="s1",
            candidate_type=ShotCandidateType.character,
            candidate_name="角色一",
            candidate_status=ShotCandidateStatus.pending,
            source="extraction",
            payload={},
        )
        candidate_2 = ShotExtractedCandidate(
            shot_id="s1",
            candidate_type=ShotCandidateType.character,
            candidate_name="角色二",
            candidate_status=ShotCandidateStatus.pending,
            source="extraction",
            payload={},
        )
        db.add_all([candidate_1, candidate_2])
        await db.flush()

        await upsert(
            db,
            body=ShotCharacterLinkCreate(shot_id="s1", character_id="char1", index=1, note="first"),
        )
        await upsert(
            db,
            body=ShotCharacterLinkCreate(shot_id="s1", character_id="char2", index=1, note="second"),
        )

        refreshed_1 = await db.get(ShotExtractedCandidate, candidate_1.id)
        refreshed_2 = await db.get(ShotExtractedCandidate, candidate_2.id)
        assert refreshed_1 is not None
        assert refreshed_2 is not None
        assert refreshed_1.candidate_status == ShotCandidateStatus.pending
        assert refreshed_1.linked_entity_id is None
        assert refreshed_1.confirmed_at is None
        assert refreshed_2.candidate_status == ShotCandidateStatus.linked
        assert refreshed_2.linked_entity_id == "char2"
    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_marks_matching_character_candidate_as_linked() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_base_graph(db)
        candidate = ShotExtractedCandidate(
            shot_id="s1",
            candidate_type=ShotCandidateType.character,
            candidate_name="角色一",
            candidate_status=ShotCandidateStatus.pending,
            source="extraction",
            payload={},
        )
        db.add(candidate)
        await db.flush()

        await upsert(
            db,
            body=ShotCharacterLinkCreate(shot_id="s1", character_id="char1", index=0, note="linked"),
        )

        refreshed = await db.get(ShotExtractedCandidate, candidate.id)
        assert refreshed is not None
        assert refreshed.candidate_status == ShotCandidateStatus.linked
        assert refreshed.linked_entity_id == "char1"
        assert refreshed.confirmed_at is not None
    await engine.dispose()
