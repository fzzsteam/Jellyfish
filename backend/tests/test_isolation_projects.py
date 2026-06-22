"""项目按 user_id 隔离测试。

验证项目 service 的 list/get/update/delete/create 全部按 user_id 过滤，
确保用户只能访问自己拥有的项目，跨用户访问按"未找到"处理。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User
from app.schemas.studio.projects import ProjectCreate, ProjectUpdate
from app.services.studio.projects import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = sm()
    db.add_all([
        User(id="u1", username="a", hashed_password="h"),
        User(id="u2", username="b", hashed_password="h"),
    ])
    await db.flush()
    return db, engine


def _create_body(project_id: str, name: str) -> ProjectCreate:
    return ProjectCreate(id=project_id, name=name, style="真人都市", visual_style="现实")


@pytest.mark.asyncio
async def test_list_projects_only_returns_own() -> None:
    db, engine = await _session()
    async with db:
        await create_project(db, _create_body("p1", "P1"), user_id="u1")
        await create_project(db, _create_body("p2", "P2"), user_id="u2")

        u1_projects, total = await list_projects(db, user_id="u1")
        assert {p.name for p in u1_projects} == {"P1"}
        assert total == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_project_rejects_other_users_project() -> None:
    db, engine = await _session()
    async with db:
        await create_project(db, _create_body("p1", "P1"), user_id="u1")

        own = await get_project(db, "p1", user_id="u1")
        assert own.id == "p1"

        with pytest.raises(HTTPException) as exc:
            await get_project(db, "p1", user_id="u2")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_project_rejects_other_users_project() -> None:
    db, engine = await _session()
    async with db:
        await create_project(db, _create_body("p1", "P1"), user_id="u1")

        with pytest.raises(HTTPException) as exc:
            await update_project(db, "p1", ProjectUpdate(name="x"), user_id="u2")
        assert exc.value.status_code == 404

        updated = await update_project(db, "p1", ProjectUpdate(name="P1-new"), user_id="u1")
        assert updated.name == "P1-new"
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_project_rejects_other_users_project() -> None:
    db, engine = await _session()
    async with db:
        await create_project(db, _create_body("p1", "P1"), user_id="u1")

        with pytest.raises(HTTPException) as exc:
            await delete_project(db, "p1", user_id="u2")
        assert exc.value.status_code == 404

        # 归属者删除成功，再次获取应 404
        await delete_project(db, "p1", user_id="u1")
        with pytest.raises(HTTPException):
            await get_project(db, "p1", user_id="u1")
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_project_assigns_user_id() -> None:
    db, engine = await _session()
    async with db:
        obj = await create_project(db, _create_body("p1", "P1"), user_id="u1")
        assert obj.user_id == "u1"
    await engine.dispose()
