"""验证业务表均带 user_id 列且为 NOT NULL（新建库语义）。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio_projects import Project
from app.models.studio_assets import Actor, Costume, Prop, Scene
from app.models.studio_prompts_files_timeline import FileItem, PromptTemplate
from app.models.task import GenerationTask

# Provider / Model 已改为全局共享（无 user_id 列），不再参与此测试。
OWNED_MODELS = [Project, Actor, Scene, Prop, Costume, FileItem, GenerationTask]


@pytest.mark.parametrize("model", OWNED_MODELS)
def test_model_has_user_id_column(model: type) -> None:
    column = model.__table__.columns.get("user_id")
    assert column is not None, f"{model.__name__} 缺少 user_id 列"
    assert column.nullable is False
    assert len(column.foreign_keys) == 1
    fk = next(iter(column.foreign_keys))
    assert fk.column.table.name == "users"


def test_prompt_template_user_id_is_nullable() -> None:
    """系统预置模板（is_system=True）全用户共享，user_id 允许为 NULL。"""
    column = PromptTemplate.__table__.columns.get("user_id")
    assert column is not None, "PromptTemplate 缺少 user_id 列"
    assert column.nullable is True
    assert len(column.foreign_keys) == 1
    fk = next(iter(column.foreign_keys))
    assert fk.column.table.name == "users"


@pytest.mark.asyncio
async def test_create_all_builds_user_id() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_local() as db:
        project = Project(id="p1", name="n", style="urban", user_id="u1")
        db.add(project)
        await db.flush()
        assert project.user_id == "u1"
    await engine.dispose()
