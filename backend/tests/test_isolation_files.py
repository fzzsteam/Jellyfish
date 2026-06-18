"""素材文件（files 表）按 user_id 隔离测试。

验证 files service 的 list/get/delete/update/download/storage-info 仅命中归属
当前用户的文件；访问他人文件按"未找到"处理。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import FileItem, FileType
from app.models.user import User
from app.schemas.studio.files import FileUpdate
from app.services.studio.files import (
    build_download_response,
    delete_file,
    get_file_detail,
    get_storage_info,
    list_files_paginated,
    update_file_meta,
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


def _file(file_id: str, name: str, *, user_id: str) -> FileItem:
    return FileItem(
        id=file_id,
        user_id=user_id,
        type=FileType.image,
        name=name,
        thumbnail="",
        tags=[],
        storage_key=f"files/{file_id}.png",
    )


@pytest.mark.asyncio
async def test_list_returns_only_own_files() -> None:
    db, engine = await _session()
    async with db:
        db.add_all([
            _file("f1", "mine", user_id="u1"),
            _file("f2", "other", user_id="u2"),
        ])
        await db.flush()
        resp = await list_files_paginated(
            db, user_id="u1", q=None, order=None, is_desc=False, page=1, page_size=10
        )
        assert resp.data is not None
        assert {i.id for i in resp.data.items} == {"f1"}
        assert resp.data.pagination.total == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_own_ok_others_404() -> None:
    db, engine = await _session()
    async with db:
        db.add_all([
            _file("f1", "mine", user_id="u1"),
            _file("f2", "other", user_id="u2"),
        ])
        await db.flush()

        assert (await get_file_detail(db, file_id="f1", user_id="u1")).id == "f1"

        with pytest.raises(HTTPException) as exc:
            await get_file_detail(db, file_id="f2", user_id="u1")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_others_file_404() -> None:
    db, engine = await _session()
    async with db:
        db.add(_file("f2", "other", user_id="u2"))
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await update_file_meta(db, file_id="f2", body=FileUpdate(name="x"), user_id="u1")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_download_others_file_404() -> None:
    db, engine = await _session()
    async with db:
        db.add(_file("f2", "other", user_id="u2"))
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await build_download_response(db, file_id="f2", user_id="u1")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_storage_info_others_file_404() -> None:
    db, engine = await _session()
    async with db:
        db.add(_file("f2", "other", user_id="u2"))
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await get_storage_info(db, file_id="f2", user_id="u1")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_others_file_noop_then_still_exists() -> None:
    db, engine = await _session()
    async with db:
        db.add(_file("f2", "other", user_id="u2"))
        await db.flush()
        # u1 删除 u2 的文件：静默 no-op，记录仍在
        await delete_file(db, file_id="f2", user_id="u1")
        assert (await db.get(FileItem, "f2")) is not None
        # u2 删除自己的文件：成功移除
        await delete_file(db, file_id="f2", user_id="u2")
        assert (await db.get(FileItem, "f2")) is None
    await engine.dispose()
