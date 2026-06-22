from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import Chapter, Character, Project, ProjectStyle, ProjectVisualStyle, Shot, ShotCharacterLink
from app.models.user import User
from app.services.studio.entity_crud import create_entity

TEST_USER_ID = "test-user"


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    # project.user_id 是 NOT NULL 外键，先插入用户行满足约束。
    db.add(User(id=TEST_USER_ID, username="test-user", hashed_password="h"))
    await db.flush()
    return db, engine


async def _seed_graph(db: AsyncSession) -> None:
    db.add_all(
        [
            Project(
                id="p1",
                name="项目一",
                description="",
                style=ProjectStyle.real_people_city,
                visual_style=ProjectVisualStyle.live_action,
                user_id=TEST_USER_ID,
            ),
            Chapter(id="c1", project_id="p1", index=1, title="第一章"),
            Chapter(id="c2", project_id="p1", index=2, title="第二章"),
            Shot(id="s1", chapter_id="c1", index=1, title="镜头一"),
        ]
    )
    await db.commit()


@pytest.mark.asyncio
async def test_create_character_with_shot_id_auto_links_shot() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_graph(db)

        payload = await create_entity(
            db,
            entity_type="character",
            user_id=TEST_USER_ID,
            body={
                "id": "char1",
                "project_id": "p1",
                "chapter_id": "c1",
                "shot_id": "s1",
                "name": "苗青",
                "description": "角色描述",
                "style": ProjectStyle.real_people_city,
                "visual_style": ProjectVisualStyle.live_action,
                "actor_id": None,
                "costume_id": None,
            },
        )

        rows = (await db.execute(select(ShotCharacterLink).where(ShotCharacterLink.shot_id == "s1"))).scalars().all()

        assert payload["id"] == "char1"
        assert len(rows) == 1
        assert rows[0].character_id == "char1"
        assert rows[0].index == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_character_rejects_mismatched_chapter_and_shot() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_graph(db)

        with pytest.raises(HTTPException, match="specified chapter"):
            await create_entity(
                db,
                entity_type="character",
                user_id=TEST_USER_ID,
                body={
                    "id": "char2",
                    "project_id": "p1",
                    "chapter_id": "c2",
                    "shot_id": "s1",
                    "name": "苗青",
                    "description": "角色描述",
                    "style": ProjectStyle.real_people_city,
                    "visual_style": ProjectVisualStyle.live_action,
                    "actor_id": None,
                    "costume_id": None,
                },
            )

        created = await db.get(Character, "char2")
        assert created is None
    await engine.dispose()
