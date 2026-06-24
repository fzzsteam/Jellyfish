"""Provider/Model 全局可见性测试。

验证 manage.py 的 provider/model CRUD 是全局操作（不按 user_id 隔离）：
- 列表返回所有记录（不区分创建者）；
- 任意合法 ID 均可获取单条；
- delete 无需归属校验，直接删除；
- ModelSettings 仍然每用户一行（不变）。
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


async def _list_providers(db: AsyncSession) -> set[str]:
    resp = await list_providers_paginated(
        db,
        q=None,
        order=None,
        is_desc=False,
        page=1,
        page_size=50,
        allow_fields={"name", "created_at", "updated_at"},
    )
    return {item.id for item in resp.data.items}


@pytest.mark.asyncio
async def test_list_providers_returns_all() -> None:
    """两个不同 created_by 创建的供应商，列表均可见。"""
    db, engine = await _session()
    async with db:
        await create_provider(db, body=_provider_body("p1"))
        await create_provider(db, body=ProviderCreate(
            id="p2", name="AliCloud", base_url="https://api.ali.com/v1", api_key="k2",
        ))

        result = await _list_providers(db)
        assert result == {"p1", "p2"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_provider_globally_visible() -> None:
    """任何合法 provider_id 均可获取，不需要归属校验。"""
    db, engine = await _session()
    async with db:
        await create_provider(db, body=_provider_body("p1"))

        provider = await get_provider(db, provider_id="p1")
        assert provider.id == "p1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_provider_not_found_raises_404() -> None:
    db, engine = await _session()
    async with db:
        with pytest.raises(HTTPException) as exc:
            await get_provider(db, provider_id="nonexistent")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_and_delete_provider_global() -> None:
    """更新和删除不需要归属校验，直接操作。"""
    db, engine = await _session()
    async with db:
        await create_provider(db, body=_provider_body("p1"))

        updated = await update_provider(db, provider_id="p1", body=ProviderUpdate(description="new"))
        assert updated.description == "new"

        await delete_provider(db, provider_id="p1")
        with pytest.raises(HTTPException):
            await get_provider(db, provider_id="p1")
    await engine.dispose()


@pytest.mark.asyncio
async def test_models_globally_visible() -> None:
    """两个不同 created_by 创建的模型，列表均可见。"""
    db, engine = await _session()
    async with db:
        await create_provider(db, body=_provider_body("p1"))
        await create_model(
            db,
            body=ModelCreate(id="m1", name="gpt-4o-mini", category="text", provider_id="p1"),
        )
        await create_model(
            db,
            body=ModelCreate(id="m2", name="gpt-4o", category="text", provider_id="p1"),
        )

        resp = await list_models_paginated(
            db,
            provider_id=None,
            category=None,
            q=None,
            order=None,
            is_desc=False,
            page=1,
            page_size=50,
            allow_fields={"name", "category", "created_at", "updated_at"},
        )
        assert {item.id for item in resp.data.items} == {"m1", "m2"}

        model = await get_model(db, model_id="m1")
        assert model.id == "m1"
    await engine.dispose()
