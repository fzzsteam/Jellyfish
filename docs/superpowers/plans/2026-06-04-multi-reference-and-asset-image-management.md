# Jellyfish Multi Reference And Asset Image Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决三个功能型问题：资产生成图全部保留并可挑选、资产管理支持批量上传本地图、`happyhorse-1.0-r2v` 支持最多 9 张参考图生成视频。

**Architecture:** 先把资产图片拆成“当前采用图”和“候选图片池”，图片生成和本地上传都只向候选池追加结果，用户显式设为当前图。视频生成在保留首帧、尾帧、关键帧旧模式的同时新增 `multi_reference`，前端按用户排序提交 1 到 9 张图，后端按顺序传给供应商。

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, TaskManager, OpenAPI generated client, React, TypeScript, Ant Design.

---

## 当前代码事实

- 图片生成结果落库在 `backend/app/services/studio/image_task_runner.py` 的 `_persist_images_to_assets`，当前只取 `result.images[0]` 并写回资产图片槽位 `file_id`。
- 通用任务链接模型在 `backend/app/models/task_links.py`，现有唯一约束不适合表达“一次任务多张候选图”。
- 资产图片 CRUD 路由在 `backend/app/api/v1/routes/studio/entities.py`。
- 资产编辑页在 `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`，已有“历史生成图片”弹窗雏形，但依赖任务链接查询，且后端只保留第一张图。
- 单文件上传接口已存在：`backend/app/api/v1/routes/studio/files.py` 的 `POST /api/v1/studio/files/upload`。
- 视频生成请求模型在 `backend/app/api/v1/routes/film/video_request.py`，`reference_mode` 仍是固定枚举。
- 视频参考图校验和自动取首尾关键帧在 `backend/app/services/studio/generation/video/build_context.py`。
- 视频运行参数构建在 `backend/app/services/film/generated_video.py`。
- 视频供应商适配在 `backend/app/core/integrations/bailian/video.py`，r2v 已使用 `reference_image` media 类型。
- 前端视频工作室在 `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`。

## 文件结构

### Backend Create

- `backend/app/models/studio_image_candidates.py`：资产/镜头图片候选表，记录候选图片与目标图片槽位的关系。
- `backend/app/schemas/studio/asset_image_candidates.py`：候选列表、创建、采用响应模型。
- `backend/app/services/studio/asset_image_candidates.py`：候选创建、查询、采用、删除服务。
- `backend/tests/test_asset_image_candidates_service.py`：候选服务单元测试。
- `backend/tests/test_asset_image_candidates_api_responses.py`：候选 API 响应测试。

### Backend Modify

- `backend/app/models/__init__.py`：导出 `AssetImageCandidate`。
- `backend/app/models/studio.py`：按现有 studio 聚合导出候选模型。
- `backend/app/schemas/studio/__init__.py`：导出候选 schemas。
- `backend/app/api/v1/routes/studio/entities.py`：增加候选查询、关联、采用、删除路由。
- `backend/app/services/studio/image_task_runner.py`：保存全部生成图并追加候选；只在空槽位自动采用第一张。
- `backend/app/api/v1/routes/film/video_request.py`：`reference_mode` 增加 `multi_reference`，`images` 描述改为支持 1 到 9。
- `backend/app/services/studio/generation/video/build_context.py`：新增多参考图校验与解析。
- `backend/app/services/studio/shot_video_readiness.py`：支持 `multi_reference` 的图片数量与供应商可用性检查。
- `backend/app/api/v1/routes/studio/shots.py`：视频 readiness 接口增加可选 `images` 查询参数。
- `backend/app/core/contracts/video_generation.py`：增加 `reference_images_base64`。
- `backend/app/services/film/generated_video.py`：把 `multi_reference` 的图片列表传入内部契约。
- `backend/app/core/integrations/bailian/video.py`：提交全部 `reference_images_base64`。
- `backend/tests/test_image_task_runner_candidates.py`：图片任务保留多张结果与不覆盖测试。
- `backend/tests/test_generated_video_service.py`：增加 `multi_reference` 校验与运行参数测试。
- `backend/tests/test_generated_video_api_responses.py`：增加请求契约测试。

### Frontend Create

- `front/src/pages/aiStudio/assets/components/AssetImageCandidateGallery.tsx`：候选图片网格、预览、设为当前图、删除候选。
- `front/src/pages/aiStudio/assets/components/AssetImageBatchUpload.tsx`：批量上传入口和进度列表。
- `front/src/pages/aiStudio/chapter/components/MultiReferenceImageSelector.tsx`：r2v 多参考图选择、排序、数量限制。

### Frontend Modify

- `front/src/services/studioEntities.ts`：增加候选池 generated client 包装方法。
- `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`：接入候选池与批量上传。
- `front/src/pages/aiStudio/assets/assetAdapters.ts`：扩展 adapter，传入候选相关能力。
- `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`：`VideoReferenceMode` 增加 `multi_reference`，接入多参考图选择器并提交最多 9 张图片。
- `front/src/services/generated/models/VideoGenerationTaskRequest.ts`：由 OpenAPI 生成，新增 `multi_reference`。
- `front/src/services/generated/services/StudioEntitiesService.ts`：由 OpenAPI 生成，新增候选池接口。

### Docs Modify

- `docs/superpowers/specs/2026-06-04-multi-reference-and-asset-image-management-design.md`：实现后按实际决策回填。
- `site/content/docs/architecture/shot-page-boundary.md`：确认工作室仍只负责生成。
- `site/content/docs/architecture/shot-status-flow.md`：说明 `multi_reference` 属于 video-readiness，不影响 `shot.status`。
- `site/content/docs/plans/creative-flow-ux-optimization.md`：加入本阶段已推进任务拆解。

---

## Task 0: 准备独立执行环境

**Files:**
- Read: `docs/superpowers/specs/2026-06-04-multi-reference-and-asset-image-management-design.md`
- Read: `docs/superpowers/plans/2026-06-04-multi-reference-and-asset-image-management.md`

- [ ] **Step 1: 检查工作树**

Run:

```powershell
git status --short
```

Expected: 明确看到当前未提交改动。执行实现时应新建独立分支或 worktree，避免和 `2026-06-03` 自动准备改动混合提交。

- [ ] **Step 2: 创建实现分支**

Run:

```powershell
git switch -c codex/multi-reference-asset-images
```

Expected: 输出 `Switched to a new branch 'codex/multi-reference-asset-images'`。

- [ ] **Step 3: 确认 API 变更会触发 OpenAPI**

Run:

```powershell
rg -n "pnpm run openapi:update|openapi:update" .
```

Expected: 找到 OpenAPI 同步命令来源。后续 Task 8 必须运行该命令。

---

## Task 1: 新增资产图片候选模型和服务

**Files:**
- Create: `backend/app/models/studio_image_candidates.py`
- Create: `backend/app/schemas/studio/asset_image_candidates.py`
- Create: `backend/app/services/studio/asset_image_candidates.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/studio.py`
- Modify: `backend/app/schemas/studio/__init__.py`
- Test: `backend/tests/test_asset_image_candidates_service.py`

- [ ] **Step 1: 写候选服务失败测试**

Create `backend/tests/test_asset_image_candidates_service.py` with tests covering append, list, adopt, and no-overwrite:

```python
"""资产图片候选池服务测试。"""

from __future__ import annotations

import pytest

from app.models.studio import Scene, SceneImage
from app.models.files import FileItem
from app.services.studio.asset_image_candidates import (
    adopt_asset_image_candidate,
    attach_asset_image_candidate,
    list_asset_image_candidates,
)


@pytest.mark.asyncio
async def test_attach_candidate_does_not_overwrite_current_image(db):
    scene = Scene(name="雨夜街道", project_id="p1")
    current_file = FileItem(id="file-current", name="current.png", type="image", path="current.png")
    candidate_file = FileItem(id="file-candidate", name="candidate.png", type="image", path="candidate.png")
    db.add_all([scene, current_file, candidate_file])
    await db.flush()
    image = SceneImage(scene_id=scene.id, file_id=current_file.id, view_angle="front", quality_level="low")
    db.add(image)
    await db.commit()

    candidate = await attach_asset_image_candidate(
        db,
        target_type="scene_image",
        target_id=image.id,
        file_id=candidate_file.id,
        source_type="upload",
        source_ref="manual",
        auto_adopt_if_empty=True,
    )
    await db.commit()

    assert candidate.file_id == candidate_file.id
    refreshed = await db.get(SceneImage, image.id)
    assert refreshed.file_id == current_file.id


@pytest.mark.asyncio
async def test_adopt_candidate_updates_current_image(db):
    scene = Scene(name="山谷", project_id="p1")
    file_obj = FileItem(id="file-new", name="new.png", type="image", path="new.png")
    db.add_all([scene, file_obj])
    await db.flush()
    image = SceneImage(scene_id=scene.id, file_id=None, view_angle="front", quality_level="low")
    db.add(image)
    await db.commit()

    candidate = await attach_asset_image_candidate(
        db,
        target_type="scene_image",
        target_id=image.id,
        file_id=file_obj.id,
        source_type="generation",
        source_ref="task-1",
        auto_adopt_if_empty=False,
    )
    adopted = await adopt_asset_image_candidate(db, candidate_id=candidate.id)
    await db.commit()

    assert adopted.file_id == file_obj.id
    refreshed = await db.get(SceneImage, image.id)
    assert refreshed.file_id == file_obj.id


@pytest.mark.asyncio
async def test_list_candidates_orders_newest_first(db):
    scene = Scene(name="城堡", project_id="p1")
    file_a = FileItem(id="file-a", name="a.png", type="image", path="a.png")
    file_b = FileItem(id="file-b", name="b.png", type="image", path="b.png")
    db.add_all([scene, file_a, file_b])
    await db.flush()
    image = SceneImage(scene_id=scene.id, file_id=None, view_angle="front", quality_level="low")
    db.add(image)
    await db.commit()

    await attach_asset_image_candidate(db, target_type="scene_image", target_id=image.id, file_id=file_a.id, source_type="generation", source_ref="task-a")
    second = await attach_asset_image_candidate(db, target_type="scene_image", target_id=image.id, file_id=file_b.id, source_type="upload", source_ref="batch-b")
    await db.commit()

    rows = await list_asset_image_candidates(db, target_type="scene_image", target_id=image.id)
    assert rows[0].id == second.id
    assert [row.file_id for row in rows] == ["file-b", "file-a"]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
uv run --project backend pytest backend/tests/test_asset_image_candidates_service.py -q
```

Expected: FAIL，原因是 `app.services.studio.asset_image_candidates` 或 `AssetImageCandidate` 尚未定义。

- [ ] **Step 3: 新增候选模型**

Create `backend/app/models/studio_image_candidates.py`:

```python
"""资产与镜头图片候选模型。

候选记录用于把生成图、本地上传图等图片文件关联到一个业务图片槽位。
图片槽位自身仍只表示当前采用图；候选池保留所有可供挑选的图片。
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class AssetImageCandidateSource(str, Enum):
    """候选图片来源。"""

    generation = "generation"
    upload = "upload"


class AssetImageCandidate(Base, TimestampMixin):
    """资产或镜头图片候选。

    target_type + target_id 指向 SceneImage、PropImage、CostumeImage、CharacterImage、
    ActorImage 或 ShotFrameImage 中的一条图片槽位记录，file_id 指向候选文件。
    """

    __tablename__ = "asset_image_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[str] = mapped_column(String(64), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default=AssetImageCandidateSource.generation.value)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "file_id", name="uq_asset_image_candidate_target_file"),
        Index("ix_asset_image_candidates_target", "target_type", "target_id"),
        Index("ix_asset_image_candidates_file_id", "file_id"),
        Index("ix_asset_image_candidates_source", "source_type", "source_ref"),
    )
```

- [ ] **Step 4: 导出候选模型**

Modify `backend/app/models/__init__.py` and `backend/app/models/studio.py` to import and export:

```python
from app.models.studio_image_candidates import AssetImageCandidate, AssetImageCandidateSource
```

Add both names to each module's `__all__`.

- [ ] **Step 5: 新增候选 schemas**

Create `backend/app/schemas/studio/asset_image_candidates.py`:

```python
"""资产图片候选 API schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AssetImageCandidateRead(BaseModel):
    """图片候选读模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    target_type: str
    target_id: int
    file_id: str
    source_type: str
    source_ref: str | None = None
    is_adopted: bool = False


class AssetImageCandidateAttachRequest(BaseModel):
    """把一个或多个文件加入目标图片槽位候选池。"""

    file_ids: list[str] = Field(..., min_length=1, max_length=100)
    source_type: str = Field("upload", pattern="^(generation|upload)$")
    source_ref: str | None = None
    auto_adopt_if_empty: bool = False


class AssetImageCandidateListRead(BaseModel):
    """图片候选列表。"""

    items: list[AssetImageCandidateRead]
```

Export these schemas from `backend/app/schemas/studio/__init__.py`.

- [ ] **Step 6: 新增候选服务**

Create `backend/app/services/studio/asset_image_candidates.py` with:

```python
"""资产图片候选服务。

该服务集中处理候选追加、候选采用与当前图更新，避免前端直接理解各类图片表。
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import FileItem
from app.models.studio import ActorImage, CharacterImage, CostumeImage, PropImage, SceneImage, ShotFrameImage
from app.models.studio_image_candidates import AssetImageCandidate

IMAGE_TARGET_MODELS = {
    "actor_image": ActorImage,
    "character_image": CharacterImage,
    "scene_image": SceneImage,
    "prop_image": PropImage,
    "costume_image": CostumeImage,
    "shot_frame_image": ShotFrameImage,
}


async def _load_target_image(db: AsyncSession, *, target_type: str, target_id: int):
    """读取目标图片槽位，并校验 target_type 合法。"""
    model = IMAGE_TARGET_MODELS.get(target_type)
    if model is None:
        raise HTTPException(status_code=400, detail=f"Unsupported image target_type: {target_type}")
    obj = await db.get(model, target_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{target_type} not found: {target_id}")
    return obj


async def list_asset_image_candidates(db: AsyncSession, *, target_type: str, target_id: int) -> list[AssetImageCandidate]:
    """按新到旧列出目标图片槽位的候选。"""
    await _load_target_image(db, target_type=target_type, target_id=target_id)
    stmt = (
        select(AssetImageCandidate)
        .where(AssetImageCandidate.target_type == target_type, AssetImageCandidate.target_id == target_id)
        .order_by(AssetImageCandidate.created_at.desc(), AssetImageCandidate.id.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def attach_asset_image_candidate(
    db: AsyncSession,
    *,
    target_type: str,
    target_id: int,
    file_id: str,
    source_type: str,
    source_ref: str | None = None,
    auto_adopt_if_empty: bool = False,
) -> AssetImageCandidate:
    """把文件加入候选池；只有空槽位且允许自动采用时才写当前图。"""
    target = await _load_target_image(db, target_type=target_type, target_id=target_id)
    file_obj = await db.get(FileItem, file_id)
    if file_obj is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

    stmt = select(AssetImageCandidate).where(
        AssetImageCandidate.target_type == target_type,
        AssetImageCandidate.target_id == target_id,
        AssetImageCandidate.file_id == file_id,
    )
    existing = (await db.execute(stmt)).scalars().first()
    if existing is not None:
        candidate = existing
    else:
        candidate = AssetImageCandidate(
            target_type=target_type,
            target_id=target_id,
            file_id=file_id,
            source_type=source_type,
            source_ref=source_ref,
        )
        db.add(candidate)
        await db.flush()

    if auto_adopt_if_empty and not getattr(target, "file_id", None):
        target.file_id = file_id
    return candidate


async def adopt_asset_image_candidate(db: AsyncSession, *, candidate_id: int) -> AssetImageCandidate:
    """采用候选图为当前图。"""
    candidate = await db.get(AssetImageCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"AssetImageCandidate not found: {candidate_id}")
    target = await _load_target_image(db, target_type=candidate.target_type, target_id=candidate.target_id)
    target.file_id = candidate.file_id
    return candidate
```

- [ ] **Step 7: 运行候选服务测试**

Run:

```powershell
uv run --project backend pytest backend/tests/test_asset_image_candidates_service.py -q
```

Expected: PASS。

- [ ] **Step 8: 提交 Task 1**

Run:

```powershell
git add backend/app/models backend/app/schemas/studio backend/app/services/studio/asset_image_candidates.py backend/tests/test_asset_image_candidates_service.py
git commit -m "feat: add asset image candidate service"
```

Expected: commit created.

---

## Task 2: 增加候选池 API

**Files:**
- Modify: `backend/app/api/v1/routes/studio/entities.py`
- Modify: `backend/app/schemas/studio/asset_image_candidates.py`
- Test: `backend/tests/test_asset_image_candidates_api_responses.py`

- [ ] **Step 1: 写 API 响应测试**

Create `backend/tests/test_asset_image_candidates_api_responses.py` with tests for:

```python
"""资产图片候选 API 响应测试。"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_attach_and_list_asset_image_candidates_api(client, db):
    response = await client.post(
        "/api/v1/studio/entities/scene/1/images/10/candidates",
        json={"file_ids": ["file-a", "file-b"], "source_type": "upload", "source_ref": "batch-1"},
    )
    assert response.status_code in {201, 404}


@pytest.mark.asyncio
async def test_adopt_asset_image_candidate_api_validates_candidate(client):
    response = await client.post("/api/v1/studio/entities/scene/1/images/10/candidates/999999/adopt")
    assert response.status_code == 404
    body = response.json()
    assert "message" in body or "detail" in body
```

If existing test fixtures expose a different async client name, follow the established fixture name in nearby API tests.

- [ ] **Step 2: 运行 API 测试确认失败**

Run:

```powershell
uv run --project backend pytest backend/tests/test_asset_image_candidates_api_responses.py -q
```

Expected: FAIL，因为候选 API 路由尚未存在。

- [ ] **Step 3: 在实体路由增加候选接口**

Modify `backend/app/api/v1/routes/studio/entities.py`:

```python
from app.schemas.studio.asset_image_candidates import AssetImageCandidateAttachRequest, AssetImageCandidateRead
from app.services.studio.asset_image_candidates import (
    adopt_asset_image_candidate,
    attach_asset_image_candidate,
    list_asset_image_candidates,
)
```

Add routes after `update_entity_image`:

```python
@router.get(
    "/{entity_type}/{entity_id}/images/{image_id}/candidates",
    response_model=ApiResponse[list[AssetImageCandidateRead]],
    summary="列出实体图片候选",
)
async def list_entity_image_candidates(entity_type: str, entity_id: str, image_id: int, db: AsyncSession = Depends(get_db)):
    target_type = f"{entity_type}_image"
    rows = await list_asset_image_candidates(db, target_type=target_type, target_id=image_id)
    return success_response([AssetImageCandidateRead.model_validate(row) for row in rows])


@router.post(
    "/{entity_type}/{entity_id}/images/{image_id}/candidates",
    response_model=ApiResponse[list[AssetImageCandidateRead]],
    status_code=status.HTTP_201_CREATED,
    summary="添加实体图片候选",
)
async def attach_entity_image_candidates(
    entity_type: str,
    entity_id: str,
    image_id: int,
    body: AssetImageCandidateAttachRequest,
    db: AsyncSession = Depends(get_db),
):
    target_type = f"{entity_type}_image"
    rows = []
    for file_id in body.file_ids:
        rows.append(
            await attach_asset_image_candidate(
                db,
                target_type=target_type,
                target_id=image_id,
                file_id=file_id,
                source_type=body.source_type,
                source_ref=body.source_ref,
                auto_adopt_if_empty=body.auto_adopt_if_empty,
            )
        )
    await db.commit()
    return created_response([AssetImageCandidateRead.model_validate(row) for row in rows])


@router.post(
    "/{entity_type}/{entity_id}/images/{image_id}/candidates/{candidate_id}/adopt",
    response_model=ApiResponse[AssetImageCandidateRead],
    summary="采用实体图片候选为当前图",
)
async def adopt_entity_image_candidate(
    entity_type: str,
    entity_id: str,
    image_id: int,
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
):
    row = await adopt_asset_image_candidate(db, candidate_id=candidate_id)
    await db.commit()
    return success_response(AssetImageCandidateRead.model_validate(row))
```

- [ ] **Step 4: 运行 API 测试**

Run:

```powershell
uv run --project backend pytest backend/tests/test_asset_image_candidates_api_responses.py -q
```

Expected: PASS。若测试客户端 fixture 名称不是 `client`，先运行 `rg -n "async def .*client|def .*client" backend/tests backend -S` 找到现有 fixture 名称，再把本测试中的 `client` 参数替换为仓库实际名称。

- [ ] **Step 5: 提交 Task 2**

Run:

```powershell
git add backend/app/api/v1/routes/studio/entities.py backend/app/schemas/studio/asset_image_candidates.py backend/tests/test_asset_image_candidates_api_responses.py
git commit -m "feat: expose asset image candidate APIs"
```

Expected: commit created.

---

## Task 3: 图片生成任务保存全部候选图

**Files:**
- Modify: `backend/app/services/studio/image_task_runner.py`
- Test: `backend/tests/test_image_task_runner_candidates.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_image_task_runner_candidates.py` with assertions:

```python
"""图片生成任务候选落库测试。"""

from __future__ import annotations

import pytest

from app.core.contracts.image_generation import ImageGenerationResult, ImageItem
from app.services.studio.image_task_runner import _persist_images_to_assets
from app.services.studio.asset_image_candidates import list_asset_image_candidates


@pytest.mark.asyncio
async def test_persist_images_to_assets_keeps_all_generated_images(db, monkeypatch):
    created_file_ids: list[str] = []

    async def fake_create_file(session, *, url, name, prefix):
        class FileObj:
            pass

        obj = FileObj()
        obj.id = f"file-{len(created_file_ids) + 1}"
        created_file_ids.append(obj.id)
        return obj

    monkeypatch.setattr("app.services.studio.image_task_runner.create_file_from_url_or_b64", fake_create_file)

    result = ImageGenerationResult(
        images=[
            ImageItem(url="https://example.com/1.png"),
            ImageItem(url="https://example.com/2.png"),
            ImageItem(url="https://example.com/3.png"),
        ]
    )
    await _persist_images_to_assets(db, task_id="task-1", relation_type="scene_image", relation_entity_id="1", result=result)

    assert created_file_ids == ["file-1", "file-2", "file-3"]
```

Before calling `_persist_images_to_assets`, create a real `Scene`、`SceneImage`、`GenerationTask` and `GenerationTaskLink` in the test database so the service can resolve `relation_type="scene_image"` and `relation_entity_id=str(scene_image.id)`.

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
uv run --project backend pytest backend/tests/test_image_task_runner_candidates.py -q
```

Expected: FAIL because only first image is currently persisted.

- [ ] **Step 3: 修改 `_persist_images_to_assets`**

In `backend/app/services/studio/image_task_runner.py`:

```python
from app.services.studio.asset_image_candidates import attach_asset_image_candidate
```

Replace first-image-only logic with:

```python
created_file_ids: list[str] = []
for index, item in enumerate(images):
    if not item.url:
        continue
    file_obj = await create_file_from_url_or_b64(
        session,
        url=item.url,
        name=f"{relation_type}-{relation_entity_id}-{index + 1}",
        prefix=f"generated-images/{relation_type}/{relation_entity_id}",
    )
    created_file_ids.append(file_obj.id)
    await attach_asset_image_candidate(
        session,
        target_type=relation_type,
        target_id=int(relation_entity_id),
        file_id=file_obj.id,
        source_type="generation",
        source_ref=task_id,
        auto_adopt_if_empty=index == 0,
    )
```

Keep existing `upsert_file_usage` behavior for each created file. Refactor the repeated relation-specific usage logic into a helper with this branch structure:

```python
async def _sync_generated_image_usage(session: AsyncSession, *, relation_type: str, relation_entity_id: str, file_id: str) -> None:
    """为生成图同步 file_usages，便于素材库和项目文件页追踪来源。"""
    if relation_type == "actor_image":
        image_row = await session.get(ActorImage, int(relation_entity_id))
        if image_row is None:
            return
        pid = await first_project_id_for_actor(session, image_row.actor_id)
        source_ref = f"actor_image:{image_row.id}"
    elif relation_type == "scene_image":
        image_row = await session.get(SceneImage, int(relation_entity_id))
        if image_row is None:
            return
        pid = await first_project_id_for_scene(session, image_row.scene_id)
        source_ref = f"scene_image:{image_row.id}"
    elif relation_type == "prop_image":
        image_row = await session.get(PropImage, int(relation_entity_id))
        if image_row is None:
            return
        pid = await first_project_id_for_prop(session, image_row.prop_id)
        source_ref = f"prop_image:{image_row.id}"
    elif relation_type == "costume_image":
        image_row = await session.get(CostumeImage, int(relation_entity_id))
        if image_row is None:
            return
        pid = await first_project_id_for_costume(session, image_row.costume_id)
        source_ref = f"costume_image:{image_row.id}"
    else:
        return

    if pid:
        await upsert_file_usage(
            session,
            file_id=file_id,
            project_id=pid,
            chapter_id=None,
            shot_id=None,
            usage_kind=FileUsageKind.asset_image,
            source_ref=source_ref,
        )
```

When updating the existing `GenerationTaskLink`, set its `file_id` to `created_file_ids[0]` for backward compatibility with existing task center and history UI.

- [ ] **Step 4: 运行图片任务测试**

Run:

```powershell
uv run --project backend pytest backend/tests/test_image_task_runner_candidates.py backend/tests/test_image_tasks_api_responses.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交 Task 3**

Run:

```powershell
git add backend/app/services/studio/image_task_runner.py backend/tests/test_image_task_runner_candidates.py
git commit -m "feat: retain all generated asset image candidates"
```

Expected: commit created.

---

## Task 4: 前端资产候选池与批量上传

**Files:**
- Create: `front/src/pages/aiStudio/assets/components/AssetImageCandidateGallery.tsx`
- Create: `front/src/pages/aiStudio/assets/components/AssetImageBatchUpload.tsx`
- Modify: `front/src/services/studioEntities.ts`
- Modify: `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`
- Modify: `front/src/pages/aiStudio/assets/assetAdapters.ts`

- [ ] **Step 1: 扩展 generated client 包装**

After OpenAPI update in Task 8 this wrapper should call generated methods. Before Task 8, write the wrapper shape in `front/src/services/studioEntities.ts`:

```ts
  listImageCandidates(entityType: EntityType, entityId: string, imageId: number) {
    return StudioEntitiesService.listEntityImageCandidatesApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdCandidatesGet({
      entityType,
      entityId,
      imageId,
    })
  },
  attachImageCandidates(entityType: EntityType, entityId: string, imageId: number, payload: Record<string, unknown>) {
    return StudioEntitiesService.attachEntityImageCandidatesApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdCandidatesPost({
      entityType,
      entityId,
      imageId,
      requestBody: payload,
    })
  },
  adoptImageCandidate(entityType: EntityType, entityId: string, imageId: number, candidateId: number) {
    return StudioEntitiesService.adoptEntityImageCandidateApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdCandidatesCandidateIdAdoptPost({
      entityType,
      entityId,
      imageId,
      candidateId,
    })
  },
```

- [ ] **Step 2: 新增候选图库组件**

Create `front/src/pages/aiStudio/assets/components/AssetImageCandidateGallery.tsx`:

```tsx
import { Button, Empty, Image, Space, Typography } from 'antd'

type AssetImageCandidate = {
  id: number
  file_id: string
  source_type: string
  source_ref?: string | null
  is_adopted?: boolean
}

type Props = {
  candidates: AssetImageCandidate[]
  resolveFileUrl: (fileId: string) => string
  loading?: boolean
  onAdopt: (candidate: AssetImageCandidate) => Promise<void>
}

export function AssetImageCandidateGallery({ candidates, resolveFileUrl, loading, onAdopt }: Props) {
  if (!loading && candidates.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无候选图片" />
  }

  return (
    <div className="asset-image-candidate-gallery">
      {candidates.map((item) => (
        <div className="asset-image-candidate-card" key={item.id}>
          <Image src={resolveFileUrl(item.file_id)} width={120} height={120} style={{ objectFit: 'cover' }} />
          <Space direction="vertical" size={4}>
            <Typography.Text type="secondary">{item.source_type === 'upload' ? '本地上传' : '生成结果'}</Typography.Text>
            <Button size="small" type={item.is_adopted ? 'default' : 'primary'} disabled={item.is_adopted} onClick={() => onAdopt(item)}>
              {item.is_adopted ? '当前采用' : '设为当前图'}
            </Button>
          </Space>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: 新增批量上传组件**

Create `front/src/pages/aiStudio/assets/components/AssetImageBatchUpload.tsx`:

```tsx
import { InboxOutlined } from '@ant-design/icons'
import { Upload, message } from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import { StudioFilesService } from '../../../../services/generated'

type Props = {
  projectId?: string | null
  sourceRef: string
  onUploaded: (fileIds: string[]) => Promise<void>
}

export function AssetImageBatchUpload({ projectId, sourceRef, onUploaded }: Props) {
  return (
    <Upload.Dragger
      multiple
      accept="image/*"
      showUploadList
      customRequest={async ({ file, onSuccess, onError }) => {
        try {
          const uploadFile = file as UploadFile
          const res = await StudioFilesService.uploadFileApiApiV1StudioFilesUploadPost({
            formData: {
              file: uploadFile as any,
              project_id: projectId ?? undefined,
              usage_kind: 'asset_image',
              source_ref: sourceRef,
            } as any,
          })
          const fileId = (res.data as any)?.id
          if (!fileId) throw new Error('上传成功但缺少 file_id')
          await onUploaded([fileId])
          onSuccess?.(res as any)
        } catch (error) {
          message.error('图片上传失败')
          onError?.(error as Error)
        }
      }}
    >
      <p className="ant-upload-drag-icon"><InboxOutlined /></p>
      <p className="ant-upload-text">批量上传本地图片</p>
    </Upload.Dragger>
  )
}
```

- [ ] **Step 4: 接入资产编辑页**

Modify `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`:

- Replace the current “历史生成图片” only-modal behavior with a visible candidate panel near the current image slot.
- On image slot selected, call `listImageCandidates`.
- On upload success, call `attachImageCandidates` with `{ file_ids, source_type: 'upload', source_ref: 'asset-upload:<imageId>' }`.
- On adopt, call `adoptImageCandidate`, then refresh asset detail, image list, and candidates.

Use this state shape:

```ts
const [imageCandidates, setImageCandidates] = useState<any[]>([])
const [candidateLoading, setCandidateLoading] = useState(false)
```

Use this refresh helper:

```ts
const refreshImageCandidates = useCallback(async (imageId: number) => {
  setCandidateLoading(true)
  try {
    const res = await adapter.listImageCandidates(assetId, imageId)
    setImageCandidates(Array.isArray(res.data) ? res.data : [])
  } finally {
    setCandidateLoading(false)
  }
}, [adapter, assetId])
```

- [ ] **Step 5: 更新资产 adapter 类型**

Modify `front/src/pages/aiStudio/assets/assetAdapters.ts` so every entity adapter exposes:

```ts
listImageCandidates: async (id: string, imageId: number) => {
  return StudioEntitiesApi.listImageCandidates('scene', id, imageId)
},
attachImageCandidates: async (id: string, imageId: number, payload: Record<string, unknown>) => {
  return StudioEntitiesApi.attachImageCandidates('scene', id, imageId, payload)
},
adoptImageCandidate: async (id: string, imageId: number, candidateId: number) => {
  return StudioEntitiesApi.adoptImageCandidate('scene', id, imageId, candidateId)
},
```

Use the correct entity type in each adapter: `actor`, `character`, `scene`, `prop`, `costume`.

- [ ] **Step 6: 前端类型检查**

Run:

```powershell
cd front
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

- [ ] **Step 7: 提交 Task 4**

Run:

```powershell
git add front/src/services/studioEntities.ts front/src/pages/aiStudio/assets
git commit -m "feat: add asset image candidates and batch upload UI"
```

Expected: commit created.

---

## Task 5: 后端支持 r2v multi_reference

**Files:**
- Modify: `backend/app/api/v1/routes/film/video_request.py`
- Modify: `backend/app/services/studio/generation/video/build_context.py`
- Modify: `backend/app/api/v1/routes/studio/shots.py`
- Modify: `backend/app/services/studio/shot_video_readiness.py`
- Modify: `backend/app/core/contracts/video_generation.py`
- Modify: `backend/app/services/film/generated_video.py`
- Modify: `backend/app/core/integrations/bailian/video.py`
- Test: `backend/tests/test_generated_video_service.py`
- Test: `backend/tests/test_generated_video_api_responses.py`

- [ ] **Step 1: 写 multi_reference 后端测试**

Append tests to `backend/tests/test_generated_video_service.py`:

```python
def test_validate_images_count_accepts_multi_reference_one_to_nine():
    validate_images_count("multi_reference", ["file-1"])
    validate_images_count("multi_reference", [f"file-{i}" for i in range(9)])


def test_validate_images_count_rejects_multi_reference_empty_or_too_many():
    with pytest.raises(HTTPException):
        validate_images_count("multi_reference", [])
    with pytest.raises(HTTPException):
        validate_images_count("multi_reference", [f"file-{i}" for i in range(10)])
```

Add a build-run-args test by copying the call style from the existing `test_build_run_args_maps_reference_images` test and changing only the reference mode, image list, and assertions:

```python
async def test_build_run_args_maps_multi_reference_images(monkeypatch):
    captured = {}

    async def fake_resolve_reference_image_refs_by_file_ids(db, *, file_ids):
        assert file_ids == ["file-1", "file-2", "file-3"]
        return [
            {"file_id": "file-1", "data_url": "data:image/png;base64,AAA"},
            {"file_id": "file-2", "data_url": "data:image/png;base64,BBB"},
            {"file_id": "file-3", "data_url": "data:image/png;base64,CCC"},
        ]

    async def fake_run_video_task(inp):
        captured["input"] = inp
        return {"url": "https://example.com/video.mp4"}

    monkeypatch.setattr(
        "app.services.film.generated_video.resolve_reference_image_refs_by_file_ids",
        fake_resolve_reference_image_refs_by_file_ids,
    )
    monkeypatch.setattr(
        "app.services.film.generated_video._run_video_task",
        fake_run_video_task,
        raising=False,
    )

    # Invoke the same public service function used by test_build_run_args_maps_reference_images,
    # with reference_mode="multi_reference" and images=["file-1", "file-2", "file-3"].
    assert captured["input"].reference_images_base64 == [
        "data:image/png;base64,AAA",
        "data:image/png;base64,BBB",
        "data:image/png;base64,CCC",
    ]
```

Do not test a private mapping helper only; this test must exercise the same service path used by normal video generation.

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
uv run --project backend pytest backend/tests/test_generated_video_service.py -q
```

Expected: FAIL because `multi_reference` is not known.

- [ ] **Step 3: 扩展请求模型**

Modify `backend/app/api/v1/routes/film/video_request.py`:

```python
reference_mode: Literal[
    "first",
    "last",
    "key",
    "first_last",
    "first_last_key",
    "multi_reference",
    "text_only",
] = Field("text_only", description="参考图模式；multi_reference 支持 1 到 9 张参考图")
images: list[str] = Field(default_factory=list, description="参考图 file_id 列表；multi_reference 支持 1 到 9 张")
```

- [ ] **Step 4: 扩展视频上下文校验**

Modify `backend/app/services/studio/generation/video/build_context.py`:

```python
MULTI_REFERENCE_MODE = "multi_reference"
MAX_MULTI_REFERENCE_IMAGES = 9
```

Update `validate_images_count`:

```python
def validate_images_count(reference_mode: str, images: list[str]) -> None:
    actual = len(images or [])
    if reference_mode == MULTI_REFERENCE_MODE:
        if actual < 1 or actual > MAX_MULTI_REFERENCE_IMAGES:
            raise HTTPException(status_code=400, detail="reference_mode=multi_reference requires 1 to 9 images")
        return
    expected = required_image_count(reference_mode)
    if actual != expected:
        raise HTTPException(status_code=400, detail=f"reference_mode={reference_mode} requires exactly {expected} images, got {actual}")
```

Update `resolve_video_reference_images` so explicit images validate and return for `multi_reference`; no implicit frame lookup is attempted for multi mode.

- [ ] **Step 5: 扩展内部视频契约**

Modify `backend/app/core/contracts/video_generation.py`:

```python
reference_images_base64: list[str] = Field(default_factory=list, max_length=9, description="r2v 多参考图，按业务提交顺序排列")
```

Update `require_prompt_or_any_reference` to include:

```python
bool(self.reference_images_base64)
```

- [ ] **Step 6: 扩展运行参数构建**

Modify `backend/app/services/film/generated_video.py`:

- For `reference_mode == "multi_reference"`, resolve every submitted file ID to data URL.
- Set `VideoGenerationInput(reference_images_base64=resolved_data_urls, prompt=prompt, model=model, ratio=ratio, seconds=seconds, seed=seed, watermark=watermark)`.
- Do not map multi-reference images into `first_frame_base64` / `last_frame_base64` / `key_frame_base64`.
- Keep old fixed modes unchanged.

- [ ] **Step 7: 扩展 Bailian r2v 适配**

Modify `backend/app/core/integrations/bailian/video.py` r2v media construction:

```python
for value in input_.reference_images_base64:
    if value:
        media.append({"type": "reference_image", "url": _as_data_url_or_remote(value)})
```

Keep existing first/last/key media append logic for old modes. If both list and legacy fields exist, append legacy fields first then list, but `generated_video.py` should avoid setting both in `multi_reference`.

- [ ] **Step 8: 扩展视频 readiness**

Modify `backend/app/api/v1/routes/studio/shots.py` readiness endpoint to accept:

```python
images: list[str] | None = Query(None, description="multi_reference 模式下用于检查的参考图 file_id 列表")
```

Modify `backend/app/services/studio/shot_video_readiness.py` so `multi_reference` validates `images` count locally and does not require first/last/key frame rows.

- [ ] **Step 9: 运行后端视频测试**

Run:

```powershell
uv run --project backend pytest backend/tests/test_generated_video_service.py backend/tests/test_generated_video_api_responses.py -q
```

Expected: PASS。

- [ ] **Step 10: 提交 Task 5**

Run:

```powershell
git add backend/app/api/v1/routes/film/video_request.py backend/app/services/studio/generation/video/build_context.py backend/app/api/v1/routes/studio/shots.py backend/app/services/studio/shot_video_readiness.py backend/app/core/contracts/video_generation.py backend/app/services/film/generated_video.py backend/app/core/integrations/bailian/video.py backend/tests/test_generated_video_service.py backend/tests/test_generated_video_api_responses.py
git commit -m "feat: support multi reference r2v generation"
```

Expected: commit created.

---

## Task 6: 前端分镜工作室支持多参考图

**Files:**
- Create: `front/src/pages/aiStudio/chapter/components/MultiReferenceImageSelector.tsx`
- Modify: `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`

- [ ] **Step 1: 新增多参考图选择器**

Create `front/src/pages/aiStudio/chapter/components/MultiReferenceImageSelector.tsx`:

```tsx
import { Button, Image, Space, Tag, Typography } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined } from '@ant-design/icons'

export type MultiReferenceImageItem = {
  fileId: string
  label: string
  url: string
}

type Props = {
  items: MultiReferenceImageItem[]
  maxCount?: number
  onChange: (items: MultiReferenceImageItem[]) => void
}

export function MultiReferenceImageSelector({ items, maxCount = 9, onChange }: Props) {
  const move = (index: number, delta: number) => {
    const next = [...items]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    const [item] = next.splice(index, 1)
    next.splice(target, 0, item)
    onChange(next)
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Typography.Text type="secondary">已选择 {items.length} / {maxCount} 张参考图</Typography.Text>
      {items.map((item, index) => (
        <div className="multi-reference-image-row" key={item.fileId}>
          <Image src={item.url} width={72} height={72} style={{ objectFit: 'cover' }} />
          <Tag>{item.label}</Tag>
          <Button icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => move(index, -1)} />
          <Button icon={<ArrowDownOutlined />} disabled={index === items.length - 1} onClick={() => move(index, 1)} />
          <Button icon={<DeleteOutlined />} danger onClick={() => onChange(items.filter((x) => x.fileId !== item.fileId))} />
        </div>
      ))}
    </Space>
  )
}
```

- [ ] **Step 2: 扩展 VideoReferenceMode**

Modify `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`:

```ts
type VideoReferenceMode = 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'multi_reference' | 'text_only'
```

- [ ] **Step 3: 增加多参考图状态**

Add state:

```ts
const [multiReferenceImages, setMultiReferenceImages] = useState<MultiReferenceImageItem[]>([])
```

Add submit derivation:

```ts
if (referenceMode === 'multi_reference') {
  const ids = multiReferenceImages.map((item) => item.fileId).filter(Boolean)
  return { referenceMode: 'multi_reference' as const, images: ids.slice(0, 9) }
}
```

- [ ] **Step 4: 添加默认推荐**

When switching to `multi_reference`, seed selected images from existing first/last/key frame file IDs:

```ts
const recommended = [
  first ? { fileId: first, label: '首帧', url: resolveFileUrl(first) } : null,
  last ? { fileId: last, label: '尾帧', url: resolveFileUrl(last) } : null,
  key ? { fileId: key, label: '关键帧', url: resolveFileUrl(key) } : null,
].filter(Boolean) as MultiReferenceImageItem[]
setMultiReferenceImages(recommended.slice(0, 9))
```

- [ ] **Step 5: 提交前校验**

Before preview or submit:

```ts
if (context.referenceMode === 'multi_reference') {
  if (context.images.length < 1) {
    message.warning('请至少选择 1 张参考图')
    return
  }
  if (context.images.length > 9) {
    message.warning('happyhorse-1.0-r2v 最多支持 9 张参考图')
    return
  }
}
```

- [ ] **Step 6: 前端类型检查**

Run:

```powershell
cd front
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

- [ ] **Step 7: 提交 Task 6**

Run:

```powershell
git add front/src/pages/aiStudio/chapter/ChapterStudio.tsx front/src/pages/aiStudio/chapter/components/MultiReferenceImageSelector.tsx
git commit -m "feat: add multi reference video selection"
```

Expected: commit created.

---

## Task 7: 同步 OpenAPI 与 generated client

**Files:**
- Modify: `front/src/services/generated/**`
- Modify: OpenAPI output files generated by the repo command

- [ ] **Step 1: 运行 OpenAPI 同步**

Run:

```powershell
pnpm run openapi:update
```

Expected: generated client includes:

- `VideoGenerationTaskRequest.reference_mode` union contains `multi_reference`.
- `StudioEntitiesService` contains candidate list, attach, adopt endpoints.
- `ShotVideoReadiness` endpoint accepts optional `images` query if implemented in Task 5.

- [ ] **Step 2: 检查 generated client**

Run:

```powershell
rg -n "multi_reference|Candidates|candidate" front/src/services/generated backend -S
```

Expected: finds generated models/services and backend route definitions.

- [ ] **Step 3: 前端类型检查**

Run:

```powershell
cd front
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

- [ ] **Step 4: 提交 Task 7**

Run:

```powershell
git add front/src/services/generated
git commit -m "chore: sync generated API client"
```

Expected: commit created.

---

## Task 8: 更新文档

**Files:**
- Modify: `docs/superpowers/specs/2026-06-04-multi-reference-and-asset-image-management-design.md`
- Modify: `site/content/docs/architecture/shot-page-boundary.md`
- Modify: `site/content/docs/architecture/shot-status-flow.md`
- Modify: `site/content/docs/plans/creative-flow-ux-optimization.md`

- [ ] **Step 1: 更新设计 spec 决策**

In `docs/superpowers/specs/2026-06-04-multi-reference-and-asset-image-management-design.md`, replace the pending decisions with the chosen decisions:

- 当前图非空时不覆盖，只进候选池。
- 空槽位时第一张生成图自动设为当前图。
- 批量上传默认只进候选池。
- 多参考图模式命名为 `multi_reference`。
- 候选池使用独立语义接口。

- [ ] **Step 2: 更新 architecture**

Update `site/content/docs/architecture/shot-page-boundary.md` with:

```markdown
## 资产图片候选与视频参考图边界

资产管理负责图片生成结果保留、本地图片导入、候选图挑选和设为当前图。分镜工作室只负责从已有镜头帧图、当前资产图和候选图中选择视频参考图，并发起视频生成。
```

Update `site/content/docs/architecture/shot-status-flow.md` with:

```markdown
`multi_reference` 是视频生成参考图模式，属于 video-readiness 判断范围，不改变 `shot.status`。`shot.status` 仍只表示分镜信息提取确认状态。
```

- [ ] **Step 3: 更新 plans**

Update `site/content/docs/plans/creative-flow-ux-optimization.md` with a section:

```markdown
## 多参考图与资产图片候选池

本阶段已推进资产图片候选池、批量本地上传和 r2v 多参考图能力。目标是让生成图和上传图都沉淀为候选，再由分镜工作室选择最多 9 张参考图提交给 `happyhorse-1.0-r2v`。
```

- [ ] **Step 4: 提交 Task 8**

Run:

```powershell
git add docs/superpowers/specs/2026-06-04-multi-reference-and-asset-image-management-design.md site/content/docs/architecture/shot-page-boundary.md site/content/docs/architecture/shot-status-flow.md site/content/docs/plans/creative-flow-ux-optimization.md
git commit -m "docs: document asset image and multi reference flow"
```

Expected: commit created.

---

## Task 9: 全量验证

**Files:**
- Read: touched backend and frontend files

- [ ] **Step 1: 后端相关测试**

Run:

```powershell
uv run --project backend pytest backend/tests/test_asset_image_candidates_service.py backend/tests/test_asset_image_candidates_api_responses.py backend/tests/test_image_task_runner_candidates.py backend/tests/test_image_tasks_api_responses.py backend/tests/test_generated_video_service.py backend/tests/test_generated_video_api_responses.py -q
```

Expected: PASS.

- [ ] **Step 2: 前端类型检查**

Run:

```powershell
cd front
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

- [ ] **Step 3: OpenAPI 变更检查**

Run:

```powershell
git diff -- front/src/services/generated | Select-String -Pattern "multi_reference|candidate|Candidates"
```

Expected: output contains the new video mode and candidate APIs.

- [ ] **Step 4: 手工验收清单**

Use local UI to verify:

- 资产管理生成多张图片后，候选池显示全部结果。
- 当前图已有值时，再生成图片不会覆盖当前图。
- 空图片槽位生成图片后，第一张图自动成为当前图。
- 资产管理可一次选择多张本地图片上传。
- 上传图片进入候选池。
- 候选图可设为当前图。
- 分镜工作室可选择 `multi_reference`。
- `multi_reference` 可提交 1 到 9 张图，超过 9 张会被前端拦截。
- 后端拒绝 0 张和超过 9 张的 `multi_reference` 请求。

- [ ] **Step 5: 最终状态检查**

Run:

```powershell
git status --short
```

Expected: only intentional uncommitted files remain, or working tree clean after commits.

---

## 风险控制

- 现有 `GenerationTaskLink` 的唯一约束不适合承载多张候选图，因此候选池应使用独立表。
- 当前仓库搜索不到明显的 Alembic 目录；执行 Task 1 时先确认部署建表方式。如果项目通过 SQLAlchemy metadata 初始化表，候选模型导出即可被纳入建表；如果部署环境另有手写建表脚本，将 `asset_image_candidates` 表结构按 Task 1 的模型字段加入该脚本。
- 前端批量上传应限制并发，建议每批同时上传不超过 3 个文件，避免浏览器和后端压力过大。
- `multi_reference` 会改变公开 API，必须执行 OpenAPI 同步。
- 任务中心只保留通用任务状态，不加入候选池详情或多参考图映射。

## 完成标准

- 生成图片全部进入候选池，用户可挑选采用。
- 当前图非空时，新生成图和上传图不会自动覆盖。
- 资产管理支持批量上传本地图片。
- `happyhorse-1.0-r2v` 可按顺序接收 1 到 9 张参考图。
- OpenAPI generated client 已同步。
- 后端相关 pytest 通过。
- 前端 `tsc --noEmit` 通过。
- architecture 与 plans 文档已同步。
