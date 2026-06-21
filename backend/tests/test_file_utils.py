from __future__ import annotations

import base64

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User
from app.utils.files import create_file_from_url_or_b64


@pytest.mark.asyncio
async def test_create_file_from_base64_assigns_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """生成文件必须显式归属用户，避免用户隔离迁移后写入 NULL。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def fake_upload_file(*, key: str, data: bytes, content_type: str | None):
        """隔离对象存储副作用，仅保留文件记录落库行为。"""
        return {"key": key, "size": len(data), "content_type": content_type}

    monkeypatch.setattr("app.utils.files.storage.upload_file", fake_upload_file)

    async with session_local() as db:
        db.add(User(id="owner-1", username="owner-1", hashed_password="x"))
        await db.commit()

        file_obj = await create_file_from_url_or_b64(
            db,
            user_id="owner-1",
            b64_data=base64.b64encode(b"image-bytes").decode(),
            name="generated",
        )

        assert file_obj.user_id == "owner-1"

    await engine.dispose()
