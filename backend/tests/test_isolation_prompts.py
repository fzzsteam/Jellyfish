"""提示词模板按 user_id 隔离测试（放行系统模板）。

验证 prompts service 的 list/get/update/delete/create 在过滤 user_id 的同时
放行 is_system=True 的系统模板：用户能看到"自己的模板 + 所有系统模板"，
但看不到别人的模板；系统模板保持禁止删改。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import PromptTemplate
from app.models.user import User
from app.schemas.studio.prompts import PromptTemplateCreate, PromptTemplateUpdate
from app.services.studio.prompts import (
    create_prompt_template,
    delete_prompt_template,
    get_prompt_template,
    list_prompt_templates,
    update_prompt_template,
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


def _tmpl(template_id: str, name: str, *, user_id: str | None, is_system: bool = False) -> PromptTemplate:
    return PromptTemplate(
        id=template_id,
        category="storyboard_prompt",
        name=name,
        content="c",
        user_id=user_id,
        is_system=is_system,
    )


@pytest.mark.asyncio
async def test_list_returns_own_and_system_not_others() -> None:
    db, engine = await _session()
    async with db:
        db.add_all([
            _tmpl("t1", "mine", user_id="u1"),
            _tmpl("t2", "other", user_id="u2"),
            _tmpl("t3", "sys", user_id=None, is_system=True),
        ])
        await db.flush()
        items, total = await list_prompt_templates(db, user_id="u1")
        assert {t.name for t in items} == {"mine", "sys"}
        assert total == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_own_and_system_ok_others_404() -> None:
    db, engine = await _session()
    async with db:
        db.add_all([
            _tmpl("t1", "mine", user_id="u1"),
            _tmpl("t2", "other", user_id="u2"),
            _tmpl("t3", "sys", user_id=None, is_system=True),
        ])
        await db.flush()

        assert (await get_prompt_template(db, "t1", user_id="u1")).id == "t1"
        assert (await get_prompt_template(db, "t3", user_id="u1")).id == "t3"

        with pytest.raises(HTTPException) as exc:
            await get_prompt_template(db, "t2", user_id="u1")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_sets_user_and_not_system() -> None:
    db, engine = await _session()
    async with db:
        body = PromptTemplateCreate(category="storyboard_prompt", name="n", content="c")
        obj = await create_prompt_template(db, body, user_id="u1")
        assert obj.user_id == "u1"
        assert obj.is_system is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_rejects_others_template_404() -> None:
    db, engine = await _session()
    async with db:
        db.add(_tmpl("t2", "other", user_id="u2"))
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await update_prompt_template(db, "t2", PromptTemplateUpdate(name="x"), user_id="u1")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_system_template_forbidden() -> None:
    db, engine = await _session()
    async with db:
        db.add(_tmpl("t3", "sys", user_id=None, is_system=True))
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await update_prompt_template(db, "t3", PromptTemplateUpdate(name="x"), user_id="u1")
        assert exc.value.status_code == 403
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_system_template_forbidden() -> None:
    db, engine = await _session()
    async with db:
        db.add(_tmpl("t3", "sys", user_id=None, is_system=True))
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await delete_prompt_template(db, "t3", user_id="u1")
        assert exc.value.status_code == 403
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_others_template_404() -> None:
    db, engine = await _session()
    async with db:
        db.add(_tmpl("t2", "other", user_id="u2"))
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await delete_prompt_template(db, "t2", user_id="u1")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_own_template_ok() -> None:
    db, engine = await _session()
    async with db:
        db.add(_tmpl("t1", "mine", user_id="u1"))
        await db.flush()
        await delete_prompt_template(db, "t1", user_id="u1")
        with pytest.raises(HTTPException):
            await get_prompt_template(db, "t1", user_id="u1")
    await engine.dispose()
