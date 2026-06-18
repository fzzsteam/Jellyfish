"""LLM provider/model/settings 按 user_id 隔离测试。

验证 manage.py 的 provider/model CRUD 与查询全部按 user_id 过滤：
- 列表只返回本人记录；
- 跨用户访问单条按"未找到"（404）处理；
- create 写入归属 user_id；
- ModelSettings 每用户一行（覆盖在 test_model_settings_per_user，这里再做最小验证）。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User
from app.schemas.llm import ModelCreate, ProviderCreate, ProviderUpdate
from app.services.llm.manage import (
    create_model,
    create_provider,
    delete_provider,
    get_model,
    get_provider,
    list_models_paginated,
    list_providers_paginated,
    update_provider,
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


def _provider_body(provider_id: str) -> ProviderCreate:
    return ProviderCreate(
        id=provider_id,
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="k",
    )


async def _list_providers(db: AsyncSession, *, user_id: str) -> set[str]:
    resp = await list_providers_paginated(
        db,
        user_id=user_id,
        q=None,
        order=None,
        is_desc=False,
        page=1,
        page_size=50,
        allow_fields={"name", "created_at", "updated_at"},
    )
    return {item.id for item in resp.data.items}


@pytest.mark.asyncio
async def test_list_providers_only_returns_own() -> None:
    db, engine = await _session()
    async with db:
        await create_provider(db, user_id="u1", body=_provider_body("p1"))
        await create_provider(db, user_id="u2", body=_provider_body("p2"))

        assert await _list_providers(db, user_id="u1") == {"p1"}
        assert await _list_providers(db, user_id="u2") == {"p2"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_provider_rejects_other_user() -> None:
    db, engine = await _session()
    async with db:
        await create_provider(db, user_id="u1", body=_provider_body("p1"))

        own = await get_provider(db, user_id="u1", provider_id="p1")
        assert own.id == "p1"
        assert own.user_id == "u1"

        with pytest.raises(HTTPException) as exc:
            await get_provider(db, user_id="u2", provider_id="p1")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_and_delete_provider_isolated() -> None:
    db, engine = await _session()
    async with db:
        await create_provider(db, user_id="u1", body=_provider_body("p1"))

        with pytest.raises(HTTPException) as exc:
            await update_provider(db, user_id="u2", provider_id="p1", body=ProviderUpdate(description="x"))
        assert exc.value.status_code == 404

        # 他人删除是静默忽略（记录仍在）
        await delete_provider(db, user_id="u2", provider_id="p1")
        assert await get_provider(db, user_id="u1", provider_id="p1") is not None

        await delete_provider(db, user_id="u1", provider_id="p1")
        with pytest.raises(HTTPException):
            await get_provider(db, user_id="u1", provider_id="p1")
    await engine.dispose()


@pytest.mark.asyncio
async def test_models_isolated_by_user() -> None:
    db, engine = await _session()
    async with db:
        await create_provider(db, user_id="u1", body=_provider_body("p1"))
        await create_provider(db, user_id="u2", body=_provider_body("p2"))
        await create_model(
            db,
            user_id="u1",
            body=ModelCreate(id="m1", name="gpt-4o-mini", category="text", provider_id="p1"),
        )
        await create_model(
            db,
            user_id="u2",
            body=ModelCreate(id="m2", name="gpt-4o-mini", category="text", provider_id="p2"),
        )

        resp = await list_models_paginated(
            db,
            user_id="u1",
            provider_id=None,
            category=None,
            q=None,
            order=None,
            is_desc=False,
            page=1,
            page_size=50,
            allow_fields={"name", "category", "created_at", "updated_at"},
        )
        assert {item.id for item in resp.data.items} == {"m1"}

        own = await get_model(db, user_id="u1", model_id="m1")
        assert own.user_id == "u1"
        with pytest.raises(HTTPException) as exc:
            await get_model(db, user_id="u2", model_id="m1")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_model_rejects_other_users_provider() -> None:
    """模型创建时 provider 必须属于同一用户，否则按 400 处理（隔离 + 输入校验）。"""
    db, engine = await _session()
    async with db:
        await create_provider(db, user_id="u1", body=_provider_body("p1"))

        with pytest.raises(HTTPException) as exc:
            await create_model(
                db,
                user_id="u2",
                body=ModelCreate(id="m_bad", name="gpt-4o-mini", category="text", provider_id="p1"),
            )
        assert exc.value.status_code == 400
    await engine.dispose()
