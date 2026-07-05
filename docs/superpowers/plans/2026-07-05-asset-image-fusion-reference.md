# 资产图片生成接入跨资产融图参考图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 资产编辑页（角色/演员/场景/道具/服装）新增独立的参考图管理区块，支持从其他资产库选图做多图融合生成，替换现有藏在描述框里的 `@` 提及机制，并修复资产生成 render-prompt 接口失真问题使生成前的预览真实可信。

**Architecture:** 后端复用现有 `build_xxx_image_submission_payload` 逻辑改造三个 render-prompt 接口，使预览与真正提交生成完全一致；前端新增 `AssetReferencePickerDrawer`（资产库选图抽屉）+ `AssetReferencePanel`（参考图卡片区，拖拽排序/替换/移除），移除 `MentionEditor`，并在 `AssetEditPageBase` 里把"点击生成"改为"预览确认后再生成"两步流程。

**Tech Stack:** FastAPI + SQLAlchemy（后端），React + TypeScript + Ant Design + react-beautiful-dnd（前端）

设计文档：`docs/superpowers/specs/2026-07-05-asset-image-fusion-reference-design.md`

---

### Task 1: 修复 `render_actor_image_prompt` 接口

**Files:**
- Modify: `backend/app/api/v1/routes/studio/image_tasks.py:244-262`
- Test: `backend/tests/test_image_tasks_api_responses.py:66-103`

- [ ] **Step 1: 替换 `test_render_actor_image_prompt_returns_success_envelope` 测试**

用 Edit 工具把这段（`backend/tests/test_image_tasks_api_responses.py` 第 66-103 行）：

```python
def test_render_actor_image_prompt_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    db = _DummyDB()

    class _Base:
        prompt = "基础演员提示词"
        default_images = ["file-1", "file-2"]
        entity_type = "actor"
        entity_id = "actor-1"
        relation_type = "actor_image"
        relation_entity_id = "1"

    class _Derived:
        prompt = "渲染后的演员提示词"
        images = ["file-1", "file-2"]

    async def _fake_build_base(*_args, **_kwargs):
        return _Base()

    def _fake_derive(*_args, **_kwargs):
        return _Derived()

    monkeypatch.setattr(route, "_build_actor_image_base_draft_service", _fake_build_base)
    monkeypatch.setattr(route, "_derive_asset_image_preview_service", _fake_derive)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/studio/image-tasks/actors/actor-1/render-prompt",
            json={"image_id": 1, "images": []},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"]["prompt"] == "渲染后的演员提示词"
    assert body["data"]["images"] == ["file-1", "file-2"]
```

替换为：

```python
def test_render_actor_image_prompt_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    db = _DummyDB()

    class _Submission:
        prompt = "陆远站在温室里，最终提示词"
        images = ["file-1", "file-2"]

    captured: dict[str, object] = {}

    async def _fake_build_submission(_db, *, actor_id, image_id, prompt, images):
        captured["actor_id"] = actor_id
        captured["image_id"] = image_id
        captured["prompt"] = prompt
        captured["images"] = images
        return _Submission()

    monkeypatch.setattr(route, "_build_actor_image_submission_payload_service", _fake_build_submission)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/studio/image-tasks/actors/actor-1/render-prompt",
            json={"image_id": 1, "prompt": "陆远站在温室里", "images": ["file-1", "file-2"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"]["prompt"] == "陆远站在温室里，最终提示词"
    assert body["data"]["images"] == ["file-1", "file-2"]
    assert captured["actor_id"] == "actor-1"
    assert captured["image_id"] == 1
    assert captured["prompt"] == "陆远站在温室里"
    assert captured["images"] == ["file-1", "file-2"]
```

- [ ] **Step 2: 运行测试确认它失败（因为 handler 还没改）**

Run: `cd backend && uv run pytest tests/test_image_tasks_api_responses.py::test_render_actor_image_prompt_returns_success_envelope -v`
Expected: FAIL（`_build_actor_image_submission_payload_service` 从未被调用，或 monkeypatch 目标属性不存在报 AttributeError）

- [ ] **Step 3: 改造 `render_actor_image_prompt` handler**

用 Edit 工具把 `backend/app/api/v1/routes/studio/image_tasks.py` 里这段（第 244-262 行）：

```python
@router.post(
    "/actors/{actor_id}/render-prompt",
    response_model=ApiResponse[RenderedPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="演员图片提示词渲染",
)
async def render_actor_image_prompt(
    actor_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[RenderedPromptResponse]:
    base = await _build_actor_image_base_draft_service(
        db,
        user_id=current_user.id,
        actor_id=actor_id,
        image_id=body.image_id,
    )
    context = _build_asset_image_context_service(base=base)
    derived = _derive_asset_image_preview_service(base=base, context=context)
    return success_response(RenderedPromptResponse(prompt=derived.prompt, images=derived.images))
```

替换为：

```python
@router.post(
    "/actors/{actor_id}/render-prompt",
    response_model=ApiResponse[RenderedPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="演员图片提示词渲染",
)
async def render_actor_image_prompt(
    actor_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[RenderedPromptResponse]:
    """预览接口必须和真正提交生成时走同一条 submission 构建逻辑，
    否则用户看到的预览会和实际生成结果不一致（历史上这里走的是另一条从数据库
    描述拼模板的路径，完全忽略请求体里的 prompt/images，属于失真的预览）。
    """
    submission = await _build_actor_image_submission_payload_service(
        db,
        actor_id=actor_id,
        image_id=body.image_id,
        prompt=body.prompt or "",
        images=body.images,
    )
    return success_response(RenderedPromptResponse(prompt=submission.prompt, images=submission.images))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_image_tasks_api_responses.py::test_render_actor_image_prompt_returns_success_envelope -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routes/studio/image_tasks.py backend/tests/test_image_tasks_api_responses.py
git commit -m "fix: 演员图片 render-prompt 接口改为复用提交路径，反映真实请求内容"
```

---

### Task 2: 修复 `render_asset_image_prompt` 接口（道具/场景/服装）

**Files:**
- Modify: `backend/app/api/v1/routes/studio/image_tasks.py:318-338`
- Test: `backend/tests/test_image_tasks_api_responses.py`（在 Task 1 新增测试之后追加）

- [ ] **Step 1: 新增 `test_render_asset_image_prompt_returns_success_envelope` 测试**

在 `backend/tests/test_image_tasks_api_responses.py` 里 `test_render_actor_image_prompt_returns_success_envelope` 函数之后插入：

```python
def test_render_asset_image_prompt_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    db = _DummyDB()

    class _Submission:
        prompt = "一把复古手枪，最终提示词"
        images = ["file-3"]

    captured: dict[str, object] = {}

    async def _fake_build_submission(_db, *, asset_type, asset_id, image_id, prompt, images):
        captured["asset_type"] = asset_type
        captured["asset_id"] = asset_id
        captured["image_id"] = image_id
        captured["prompt"] = prompt
        captured["images"] = images
        return _Submission()

    monkeypatch.setattr(route, "_build_asset_image_submission_payload_service", _fake_build_submission)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/studio/image-tasks/assets/prop/prop-1/render-prompt",
            json={"image_id": 2, "prompt": "一把复古手枪", "images": ["file-3"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"]["prompt"] == "一把复古手枪，最终提示词"
    assert body["data"]["images"] == ["file-3"]
    assert captured["asset_type"] == "prop"
    assert captured["asset_id"] == "prop-1"
    assert captured["image_id"] == 2
    assert captured["prompt"] == "一把复古手枪"
    assert captured["images"] == ["file-3"]
```

- [ ] **Step 2: 运行测试确认它失败**

Run: `cd backend && uv run pytest tests/test_image_tasks_api_responses.py::test_render_asset_image_prompt_returns_success_envelope -v`
Expected: FAIL

- [ ] **Step 3: 改造 `render_asset_image_prompt` handler**

把 `backend/app/api/v1/routes/studio/image_tasks.py` 里这段（第 318-338 行）：

```python
@router.post(
    "/assets/{asset_type}/{asset_id}/render-prompt",
    response_model=ApiResponse[RenderedPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="道具/场景/服装图片提示词渲染",
)
async def render_asset_image_prompt(
    asset_type: str,
    asset_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[RenderedPromptResponse]:
    base = await _build_asset_image_base_draft_service(
        db,
        user_id=current_user.id,
        asset_type=asset_type,
        asset_id=asset_id,
        image_id=body.image_id,
    )
    context = _build_asset_image_context_service(base=base)
    derived = _derive_asset_image_preview_service(base=base, context=context)
    return success_response(RenderedPromptResponse(prompt=derived.prompt, images=derived.images))
```

替换为：

```python
@router.post(
    "/assets/{asset_type}/{asset_id}/render-prompt",
    response_model=ApiResponse[RenderedPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="道具/场景/服装图片提示词渲染",
)
async def render_asset_image_prompt(
    asset_type: str,
    asset_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[RenderedPromptResponse]:
    """预览必须复用与提交生成相同的 submission 构建逻辑，原因同 render_actor_image_prompt。"""
    submission = await _build_asset_image_submission_payload_service(
        db,
        asset_type=asset_type,
        asset_id=asset_id,
        image_id=body.image_id,
        prompt=body.prompt or "",
        images=body.images,
    )
    return success_response(RenderedPromptResponse(prompt=submission.prompt, images=submission.images))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_image_tasks_api_responses.py::test_render_asset_image_prompt_returns_success_envelope -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routes/studio/image_tasks.py backend/tests/test_image_tasks_api_responses.py
git commit -m "fix: 道具/场景/服装图片 render-prompt 接口改为复用提交路径"
```

---

### Task 3: 修复 `render_character_image_prompt` 接口

**Files:**
- Modify: `backend/app/api/v1/routes/studio/image_tasks.py:390-408`
- Test: `backend/tests/test_image_tasks_api_responses.py`（在 Task 2 新增测试之后追加）

- [ ] **Step 1: 新增 `test_render_character_image_prompt_returns_success_envelope` 测试**

在 `test_render_asset_image_prompt_returns_success_envelope` 函数之后插入：

```python
def test_render_character_image_prompt_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    db = _DummyDB()

    class _Submission:
        prompt = "小明的正面立绘，最终提示词"
        images: list[str] = []

    captured: dict[str, object] = {}

    async def _fake_build_submission(_db, *, character_id, image_id, prompt, images):
        captured["character_id"] = character_id
        captured["image_id"] = image_id
        captured["prompt"] = prompt
        captured["images"] = images
        return _Submission()

    monkeypatch.setattr(route, "_build_character_image_submission_payload_service", _fake_build_submission)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/studio/image-tasks/characters/character-1/render-prompt",
            json={"image_id": 3, "prompt": "小明的正面立绘", "images": []},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"]["prompt"] == "小明的正面立绘，最终提示词"
    assert body["data"]["images"] == []
    assert captured["character_id"] == "character-1"
    assert captured["image_id"] == 3
    assert captured["prompt"] == "小明的正面立绘"
```

- [ ] **Step 2: 运行测试确认它失败**

Run: `cd backend && uv run pytest tests/test_image_tasks_api_responses.py::test_render_character_image_prompt_returns_success_envelope -v`
Expected: FAIL

- [ ] **Step 3: 改造 `render_character_image_prompt` handler**

把 `backend/app/api/v1/routes/studio/image_tasks.py` 里这段（第 390-408 行）：

```python
@router.post(
    "/characters/{character_id}/render-prompt",
    response_model=ApiResponse[RenderedPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="角色图片提示词渲染",
)
async def render_character_image_prompt(
    character_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[RenderedPromptResponse]:
    base = await _build_character_image_base_draft_service(
        db,
        user_id=current_user.id,
        character_id=character_id,
        image_id=body.image_id,
    )
    context = _build_asset_image_context_service(base=base)
    derived = _derive_asset_image_preview_service(base=base, context=context)
    return success_response(RenderedPromptResponse(prompt=derived.prompt, images=derived.images))
```

替换为：

```python
@router.post(
    "/characters/{character_id}/render-prompt",
    response_model=ApiResponse[RenderedPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="角色图片提示词渲染",
)
async def render_character_image_prompt(
    character_id: str,
    body: StudioImageTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[RenderedPromptResponse]:
    """预览必须复用与提交生成相同的 submission 构建逻辑，原因同 render_actor_image_prompt。"""
    submission = await _build_character_image_submission_payload_service(
        db,
        character_id=character_id,
        image_id=body.image_id,
        prompt=body.prompt or "",
        images=body.images,
    )
    return success_response(RenderedPromptResponse(prompt=submission.prompt, images=submission.images))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_image_tasks_api_responses.py::test_render_character_image_prompt_returns_success_envelope -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routes/studio/image_tasks.py backend/tests/test_image_tasks_api_responses.py
git commit -m "fix: 角色图片 render-prompt 接口改为复用提交路径"
```

---

### Task 4: 清理不再使用的 import 并跑通全量后端测试

**Files:**
- Modify: `backend/app/api/v1/routes/studio/image_tasks.py:26-37`

- [ ] **Step 1: 删除三个不再被调用的 base-draft/context/preview 导入**

Task 1-3 完成后，`_build_actor_image_base_draft_service`、`_build_asset_image_base_draft_service`、`_build_character_image_base_draft_service`、`_build_asset_image_context_service`、`_derive_asset_image_preview_service` 在 `image_tasks.py` 里不再被任何 handler 调用（`unused-import` 检查未在 pylintrc 里禁用，需要清理）。

把这段（第 26-37 行）：

```python
from app.services.studio.generation.asset_image import (
    build_actor_image_base_draft as _build_actor_image_base_draft_service,
    build_actor_image_submission_payload as _build_actor_image_submission_payload_service,
    build_asset_image_base_draft as _build_asset_image_base_draft_service,
    build_asset_image_context as _build_asset_image_context_service,
    build_asset_image_submission_payload as _build_asset_image_submission_payload_service,
    build_character_image_base_draft as _build_character_image_base_draft_service,
    build_character_image_submission_payload as _build_character_image_submission_payload_service,
    derive_asset_image_preview as _derive_asset_image_preview_service,
)
```

替换为：

```python
from app.services.studio.generation.asset_image import (
    build_actor_image_submission_payload as _build_actor_image_submission_payload_service,
    build_asset_image_submission_payload as _build_asset_image_submission_payload_service,
    build_character_image_submission_payload as _build_character_image_submission_payload_service,
)
```

- [ ] **Step 2: 语法检查**

Run: `cd backend && python -m py_compile app/api/v1/routes/studio/image_tasks.py`
Expected: 无输出（成功）

- [ ] **Step 3: 跑全量后端测试**

Run: `cd backend && uv run pytest -q`
Expected: 除已知的 11 个 pre-existing 失败（ApiResponse meta / ShotDetail mock 相关，与本次改动无关）外全部通过。若失败数超过 11 个或失败内容涉及 `image_tasks`，需要排查修复。

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/routes/studio/image_tasks.py
git commit -m "refactor: 清理 render-prompt 改造后不再使用的 base-draft 导入"
```

---

### Task 5: 新建 `AssetReferencePickerDrawer` 组件

**Files:**
- Create: `front/src/pages/aiStudio/assets/components/AssetReferencePickerDrawer.tsx`

- [ ] **Step 1: 写入组件文件**

```tsx
/**
 * AssetReferencePickerDrawer — 资产编辑页专用的参考图选择抽屉
 *
 * 在资产编辑页新增/替换参考图时弹出。右侧半屏 Drawer，按角色/演员/场景/道具/服装
 * 5 种资产类型分 tab 展示资产库列表，支持搜索；选中后直接从列表项的 thumbnail
 * 字段解析出 file_id 并回调，不需要再单独请求资产详情。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Drawer, Empty, Input, Segmented, Spin, message } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { StudioEntitiesService } from '../../../../services/generated'
import { resolveAssetUrl, tryExtractFileIdFromUrl } from '../utils'

export type AssetReferenceKind = 'character' | 'actor' | 'scene' | 'prop' | 'costume'

export type AssetReferenceOption = {
  kind: AssetReferenceKind
  entityId: string
  entityName: string
  file_id: string
}

type PickerItem = {
  id: string
  name: string
  thumbnail?: string | null
  description?: string | null
}

const KIND_LABEL: Record<AssetReferenceKind, string> = {
  character: '角色',
  actor: '演员',
  scene: '场景',
  prop: '道具',
  costume: '服装',
}

const KIND_OPTIONS: Array<{ label: string; value: AssetReferenceKind }> = [
  { label: '角色', value: 'character' },
  { label: '演员', value: 'actor' },
  { label: '场景', value: 'scene' },
  { label: '道具', value: 'prop' },
  { label: '服装', value: 'costume' },
]

const PAGE_SIZE = 20

// 从资产列表接口返回的 thumbnail 字段（可能是下载 URL、或裸 file_id）里解析出 file_id。
function resolveFileId(thumbnail?: string | null): string | null {
  if (!thumbnail) return null
  return tryExtractFileIdFromUrl(thumbnail) ?? (!thumbnail.includes('/') && !thumbnail.includes(':') ? thumbnail : null)
}

type AssetReferencePickerDrawerProps = {
  open: boolean
  /** 抽屉打开时默认选中的资产类型 tab；替换场景可传入被替换项的 kind。 */
  initialKind?: AssetReferenceKind
  onSelect: (option: AssetReferenceOption) => void
  onClose: () => void
}

export function AssetReferencePickerDrawer({
  open,
  initialKind = 'scene',
  onSelect,
  onClose,
}: AssetReferencePickerDrawerProps) {
  const [activeKind, setActiveKind] = useState<AssetReferenceKind>(initialKind)
  const [searchText, setSearchText] = useState('')
  const [items, setItems] = useState<PickerItem[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [fetching, setFetching] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const searchTimerRef = useRef<number | null>(null)

  const fetchItems = useCallback(
    async (kind: AssetReferenceKind, q: string, p: number, append: boolean) => {
      setFetching(true)
      try {
        const res = await StudioEntitiesService.listEntitiesApiV1StudioEntitiesEntityTypeGet({
          entityType: kind,
          q: q || null,
          page: p,
          pageSize: PAGE_SIZE,
          projectId: null,
        })
        const data = res.data
        if (!data) return
        const mapped: PickerItem[] = (data.items ?? []).map((raw: Record<string, unknown>) => ({
          id: String(raw.id ?? ''),
          name: String(raw.name ?? ''),
          thumbnail: (raw.thumbnail as string | null) ?? null,
          description: (raw.description as string | null) ?? null,
        }))
        setItems((prev) => (append ? [...prev, ...mapped] : mapped))
        setTotal(data.pagination?.total ?? 0)
        setPage(p)
      } catch {
        // 静默失败，保留上一次的列表状态
      } finally {
        setFetching(false)
      }
    },
    [],
  )

  // 每次打开或 initialKind 变更时重置到默认 tab 并清空筛选状态。
  useEffect(() => {
    if (!open) return
    setActiveKind(initialKind)
    setSearchText('')
    setSelectedId(null)
    setPage(1)
    setItems([])
  }, [open, initialKind])

  // 资产类型切换时重新拉取列表。
  useEffect(() => {
    if (!open) return
    setSearchText('')
    setSelectedId(null)
    setPage(1)
    setItems([])
    fetchItems(activeKind, '', 1, false)
  }, [open, activeKind, fetchItems])

  const handleSearch = (val: string) => {
    setSearchText(val)
    if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current)
    searchTimerRef.current = window.setTimeout(() => {
      setItems([])
      setPage(1)
      fetchItems(activeKind, val, 1, false)
    }, 400)
  }

  const handleLoadMore = () => {
    fetchItems(activeKind, searchText, page + 1, true)
  }

  const hasMore = items.length < total

  const handleConfirm = () => {
    if (!selectedId) return
    const item = items.find((i) => i.id === selectedId)
    if (!item) return
    const fileId = resolveFileId(item.thumbnail)
    if (!fileId) {
      message.warning('该资产暂无可用图片，无法作为参考图')
      return
    }
    onSelect({ kind: activeKind, entityId: item.id, entityName: item.name, file_id: fileId })
  }

  return (
    <Drawer
      title="添加参考图"
      placement="right"
      width="50%"
      open={open}
      onClose={onClose}
      destroyOnClose
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" disabled={!selectedId} onClick={handleConfirm}>
            确认添加
          </Button>
        </div>
      }
    >
      <div className="flex flex-col h-full gap-4">
        <Segmented
          block
          value={activeKind}
          onChange={(value) => setActiveKind(value as AssetReferenceKind)}
          options={KIND_OPTIONS}
        />

        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={`搜索${KIND_LABEL[activeKind]}名称或描述`}
          value={searchText}
          onChange={(e) => handleSearch(e.target.value)}
          allowClear
        />

        {fetching && items.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <Spin />
          </div>
        ) : items.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <Empty description={`暂无${KIND_LABEL[activeKind]}资产`} />
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {items.map((item) => {
                const isSelected = selectedId === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(isSelected ? null : item.id)}
                    className={[
                      'relative flex flex-col rounded-lg border-2 overflow-hidden text-left transition-all cursor-pointer',
                      isSelected
                        ? 'border-blue-500 shadow-md ring-2 ring-blue-200'
                        : 'border-slate-200 hover:border-slate-400',
                    ].join(' ')}
                  >
                    <div className="w-full aspect-square bg-slate-100 overflow-hidden">
                      {item.thumbnail ? (
                        <img
                          src={resolveAssetUrl(item.thumbnail) ?? ''}
                          alt={item.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">
                          暂无图片
                        </div>
                      )}
                    </div>
                    <div className="px-2 py-1.5">
                      <div className="text-xs font-medium text-slate-800 truncate">{item.name}</div>
                      {item.description ? (
                        <div className="text-[11px] text-slate-500 truncate mt-0.5">{item.description}</div>
                      ) : null}
                    </div>
                    {isSelected ? (
                      <div className="absolute top-1.5 left-1.5 bg-blue-500 text-white text-[10px] rounded px-1 py-0.5 leading-tight">
                        已选
                      </div>
                    ) : null}
                  </button>
                )
              })}
            </div>

            {hasMore ? (
              <div className="mt-4 flex justify-center">
                <Button size="small" loading={fetching} onClick={handleLoadMore}>
                  加载更多（还剩 {total - items.length}）
                </Button>
              </div>
            ) : null}

            {fetching && items.length > 0 ? (
              <div className="mt-4 flex justify-center">
                <Spin size="small" />
              </div>
            ) : null}
          </div>
        )}
      </div>
    </Drawer>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add front/src/pages/aiStudio/assets/components/AssetReferencePickerDrawer.tsx
git commit -m "feat: 新增资产编辑页参考图选择抽屉 AssetReferencePickerDrawer"
```

---

### Task 6: 新建 `AssetReferencePanel` 组件

**Files:**
- Create: `front/src/pages/aiStudio/assets/components/AssetReferencePanel.tsx`

- [ ] **Step 1: 写入组件文件**

```tsx
/**
 * AssetReferencePanel — 资产编辑页的参考图管理区块
 *
 * 展示当前已选中的参考图（均来自其他资产），支持拖拽调整顺序、替换、移除、
 * 点击放大预览。参考图顺序会原样传给生成接口的 images 字段。
 */

import { useEffect, useState } from 'react'
import { Button, Image, Tag, Tooltip } from 'antd'
import { HolderOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { DragDropContext, Draggable, Droppable, type DroppableProps, type DropResult } from 'react-beautiful-dnd'
import { buildFileDownloadUrl } from '../utils'
import type { AssetReferenceKind, AssetReferenceOption } from './AssetReferencePickerDrawer'

const KIND_LABEL: Record<AssetReferenceKind, string> = {
  character: '角色',
  actor: '演员',
  scene: '场景',
  prop: '道具',
  costume: '服装',
}

function reorder<T>(list: T[], startIndex: number, endIndex: number): T[] {
  const result = list.slice()
  const [removed] = result.splice(startIndex, 1)
  result.splice(endIndex, 0, removed)
  return result
}

// react-beautiful-dnd 在 React 18 StrictMode 下首帧渲染会报错，延后一帧启用 Droppable 规避。
function StrictModeDroppable({ children, ...props }: DroppableProps) {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    const animation = requestAnimationFrame(() => setEnabled(true))
    return () => {
      cancelAnimationFrame(animation)
      setEnabled(false)
    }
  }, [])

  if (!enabled) return null
  return <Droppable {...props}>{children}</Droppable>
}

type AssetReferencePanelProps = {
  options: AssetReferenceOption[]
  selectedFileIds: string[]
  onChangeSelectedFileIds: (fileIds: string[]) => void
  onAddFromLibrary: () => void
  onReplaceFromLibrary: (fileId: string) => void
  disabled?: boolean
}

export function AssetReferencePanel({
  options,
  selectedFileIds,
  onChangeSelectedFileIds,
  onAddFromLibrary,
  onReplaceFromLibrary,
  disabled = false,
}: AssetReferencePanelProps) {
  const [previewFileId, setPreviewFileId] = useState<string | null>(null)

  const optionByFileId = new Map(options.map((option) => [option.file_id, option]))

  const removeFileId = (fileId: string) => {
    onChangeSelectedFileIds(selectedFileIds.filter((id) => id !== fileId))
  }

  const handleDragEnd = (result: DropResult) => {
    if (!result.destination) return
    if (result.destination.index === result.source.index) return
    onChangeSelectedFileIds(reorder(selectedFileIds, result.source.index, result.destination.index))
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-slate-900">参考图</div>
          <div className="mt-1 text-xs text-slate-500">从资产库选择其他资产的图片作为参考，多张参考图会一起融合生成。</div>
        </div>
        <Button size="small" icon={<PlusOutlined />} disabled={disabled} onClick={onAddFromLibrary}>
          添加参考图
        </Button>
      </div>
      {selectedFileIds.length === 0 ? (
        <div className="text-xs text-gray-400">暂无参考图，可点击"添加参考图"从资产库新增</div>
      ) : (
        <DragDropContext onDragEnd={handleDragEnd}>
          <StrictModeDroppable droppableId="asset-reference-files" direction="horizontal">
            {(provided) => (
              <div ref={provided.innerRef} {...provided.droppableProps} className="flex gap-3 overflow-x-auto pb-2">
                {selectedFileIds.map((fid, index) => {
                  const option = optionByFileId.get(fid)
                  return (
                    <Draggable key={fid} draggableId={fid} index={index}>
                      {(dragProvided, snapshot) => (
                        <div
                          ref={dragProvided.innerRef}
                          {...dragProvided.draggableProps}
                          className={[
                            'w-[132px] shrink-0 rounded-lg border bg-white p-2 shadow-sm transition-shadow',
                            snapshot.isDragging ? 'border-blue-400 shadow-md' : 'border-slate-200',
                          ].join(' ')}
                        >
                          <div className="mb-1 flex items-center justify-between gap-1">
                            {option ? <Tag className="!m-0" color="default">{KIND_LABEL[option.kind]}</Tag> : <span />}
                            <span className="inline-flex h-6 w-6 items-center justify-center rounded text-slate-400" aria-hidden="true">
                              <HolderOutlined />
                            </span>
                          </div>
                          <Tooltip title="按住图片拖拽调整顺序">
                            <div
                              {...dragProvided.dragHandleProps}
                              className="group relative h-[78px] w-[116px] cursor-grab overflow-hidden rounded-lg border border-slate-200 bg-slate-100 active:cursor-grabbing"
                            >
                              <img
                                src={buildFileDownloadUrl(fid)}
                                alt={option?.entityName ?? `参考图${index + 1}`}
                                className="h-full w-full select-none object-cover"
                                draggable={false}
                              />
                              <button
                                type="button"
                                className="absolute right-1 top-1 inline-flex h-6 w-6 items-center justify-center rounded bg-white/90 text-slate-600 shadow-sm transition hover:bg-white hover:text-blue-600"
                                aria-label="预览参考图"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  setPreviewFileId(fid)
                                }}
                              >
                                <SearchOutlined className="text-xs" />
                              </button>
                            </div>
                          </Tooltip>
                          <div className="mt-2 truncate text-[11px] text-gray-700">{option?.entityName ?? fid}</div>
                          <div className="mt-2 flex gap-1">
                            <Button size="small" className="flex-1" disabled={disabled} onClick={() => onReplaceFromLibrary(fid)}>
                              替换
                            </Button>
                            <Button size="small" danger disabled={disabled} onClick={() => removeFileId(fid)}>
                              移除
                            </Button>
                          </div>
                        </div>
                      )}
                    </Draggable>
                  )
                })}
                {provided.placeholder}
              </div>
            )}
          </StrictModeDroppable>
        </DragDropContext>
      )}
      <Image
        src={previewFileId ? buildFileDownloadUrl(previewFileId) : undefined}
        style={{ display: 'none' }}
        preview={{
          visible: !!previewFileId,
          src: previewFileId ? buildFileDownloadUrl(previewFileId) : undefined,
          onVisibleChange: (visible) => {
            if (!visible) setPreviewFileId(null)
          },
        }}
      />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add front/src/pages/aiStudio/assets/components/AssetReferencePanel.tsx
git commit -m "feat: 新增资产编辑页参考图管理区块 AssetReferencePanel"
```

---

### Task 7: 给 5 种资产类型适配器新增 `renderPromptPreview`

**Files:**
- Modify: `front/src/pages/aiStudio/assets/assetAdapters.ts`
- Modify: `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx:88-138`（新增 prop 类型）

- [ ] **Step 1: 在 `AssetEditPageBaseProps` 里新增 `renderPromptPreview` 字段**

把 `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx` 里这段（第 121-138 行）：

```ts
export type AssetEditPageBaseProps<TAsset extends BaseAsset, TImage extends BaseAssetImage> = {
  assetId?: string
  missingAssetIdText: string
  assetDisplayName: string
  backTo: string
  relationType: string
  getAsset: (assetId: string) => Promise<TAsset | null>
  updateAsset: (assetId: string, payload: AssetUpdate) => Promise<TAsset | null>
  listImages: (assetId: string) => Promise<TImage[]>
  createImageSlot: (assetId: string, angle: AssetViewAngle) => Promise<void>
  updateImage: (assetId: string, imageId: number, payload: { file_id: string; width?: number | null; height?: number | null; format?: string | null }) => Promise<void>
  listImageCandidates: (assetId: string, imageId: number) => Promise<AssetImageCandidateRead[]>
  adoptImageCandidate: (assetId: string, imageId: number, candidateId: number) => Promise<void>
  deleteImageCandidate: (assetId: string, imageId: number, candidateId: number) => Promise<void>
  createGenerationTask: (assetId: string, imageId: number, payload: ImageGenerationPayload) => Promise<string | null>
  attachImageCandidates?: (assetId: string, imageId: number, fileIds: string[]) => Promise<void>
  onNavigate: (to: string, replace?: boolean) => void
}
```

替换为：

```ts
export type RenderedPromptPreview = {
  prompt: string
  images: string[]
}

export type AssetEditPageBaseProps<TAsset extends BaseAsset, TImage extends BaseAssetImage> = {
  assetId?: string
  missingAssetIdText: string
  assetDisplayName: string
  backTo: string
  relationType: string
  getAsset: (assetId: string) => Promise<TAsset | null>
  updateAsset: (assetId: string, payload: AssetUpdate) => Promise<TAsset | null>
  listImages: (assetId: string) => Promise<TImage[]>
  createImageSlot: (assetId: string, angle: AssetViewAngle) => Promise<void>
  updateImage: (assetId: string, imageId: number, payload: { file_id: string; width?: number | null; height?: number | null; format?: string | null }) => Promise<void>
  listImageCandidates: (assetId: string, imageId: number) => Promise<AssetImageCandidateRead[]>
  adoptImageCandidate: (assetId: string, imageId: number, candidateId: number) => Promise<void>
  deleteImageCandidate: (assetId: string, imageId: number, candidateId: number) => Promise<void>
  createGenerationTask: (assetId: string, imageId: number, payload: ImageGenerationPayload) => Promise<string | null>
  // 生成前的预览：复用与创建生成任务相同的后端 submission 逻辑，保证预览与实际生成一致。
  renderPromptPreview: (assetId: string, imageId: number, payload: { prompt: string; images: string[] }) => Promise<RenderedPromptPreview | null>
  attachImageCandidates?: (assetId: string, imageId: number, fileIds: string[]) => Promise<void>
  onNavigate: (to: string, replace?: boolean) => void
}
```

- [ ] **Step 2: 给 5 个适配器新增 `renderPromptPreview`（character 变体）**

在 `front/src/pages/aiStudio/assets/assetAdapters.ts` 的 `character` 适配器里，紧跟在 `createGenerationTask` 字段（第 70-83 行）之后新增：

```ts
    renderPromptPreview: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.renderCharacterImagePromptApiV1StudioImageTasksCharactersCharacterIdRenderPromptPost({
        characterId: id,
        requestBody: {
          image_id: imageId,
          prompt: payload.prompt,
          images: payload.images,
        },
      })
      return res.data ? { prompt: res.data.prompt, images: res.data.images ?? [] } : null
    },
```

- [ ] **Step 3: 给 `actor` 适配器新增 `renderPromptPreview`**

在 `actor` 适配器的 `createGenerationTask` 字段（第 121-134 行）之后新增：

```ts
    renderPromptPreview: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.renderActorImagePromptApiV1StudioImageTasksActorsActorIdRenderPromptPost({
        actorId: id,
        requestBody: {
          image_id: imageId,
          prompt: payload.prompt,
          images: payload.images,
        },
      })
      return res.data ? { prompt: res.data.prompt, images: res.data.images ?? [] } : null
    },
```

- [ ] **Step 4: 给 `scene`/`prop`/`costume` 三个适配器分别新增 `renderPromptPreview`**

在 `scene` 适配器的 `createGenerationTask` 字段（第 172-186 行）之后新增：

```ts
    renderPromptPreview: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.renderAssetImagePromptApiV1StudioImageTasksAssetsAssetTypeAssetIdRenderPromptPost({
        assetType: 'scene',
        assetId: id,
        requestBody: {
          image_id: imageId,
          prompt: payload.prompt,
          images: payload.images,
        },
      })
      return res.data ? { prompt: res.data.prompt, images: res.data.images ?? [] } : null
    },
```

在 `prop` 适配器的 `createGenerationTask` 字段（第 224-238 行）之后新增：

```ts
    renderPromptPreview: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.renderAssetImagePromptApiV1StudioImageTasksAssetsAssetTypeAssetIdRenderPromptPost({
        assetType: 'prop',
        assetId: id,
        requestBody: {
          image_id: imageId,
          prompt: payload.prompt,
          images: payload.images,
        },
      })
      return res.data ? { prompt: res.data.prompt, images: res.data.images ?? [] } : null
    },
```

在 `costume` 适配器的 `createGenerationTask` 字段（第 276-290 行）之后新增：

```ts
    renderPromptPreview: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.renderAssetImagePromptApiV1StudioImageTasksAssetsAssetTypeAssetIdRenderPromptPost({
        assetType: 'costume',
        assetId: id,
        requestBody: {
          image_id: imageId,
          prompt: payload.prompt,
          images: payload.images,
        },
      })
      return res.data ? { prompt: res.data.prompt, images: res.data.images ?? [] } : null
    },
```

- [ ] **Step 5: 运行 typecheck 确认新增字段没有破坏类型（此时 `AssetEditPageBase` 组件本身尚未消费新 prop，属正常中间态，不应报错）**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 无新增类型错误（可能仍有 Task 8/9/10 完成前的过渡态错误——若有，先确认错误信息只与本任务无关的既有代码相关）

- [ ] **Step 6: Commit**

```bash
git add front/src/pages/aiStudio/assets/assetAdapters.ts front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx
git commit -m "feat: 5 种资产类型适配器新增 renderPromptPreview，接入 render-prompt 接口"
```

---

### Task 8: 移除 `AssetEditPageBase` 里的 `@` 提及机制

**Files:**
- Modify: `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`

- [ ] **Step 1: 删除 `MentionEditor` 相关 import**

把（第 24-25 行）：

```ts
import { MentionEditor } from './MentionEditor'
import type { MentionAssetKind, MentionImageOption } from './MentionEditor'
```

删除（不替换任何内容）。

- [ ] **Step 2: 删除 `ASSET_MENTION_PAGE_SIZE` 常量**

把（第 47 行）：

```ts
const ASSET_MENTION_PAGE_SIZE = 100
```

删除。

- [ ] **Step 3: 删除 `MentionEntityRecord`/`MentionImageRecord` 类型**

把（第 108-119 行）：

```ts
type MentionEntityRecord = {
  id?: string
  name?: string | null
  title?: string | null
}

type MentionImageRecord = {
  id?: number | string
  file_id?: string | null
  view_angle?: string | null
  name?: string | null
}
```

删除。

- [ ] **Step 4: 删除 `listMentionEntities`/`listMentionEntityImages` 辅助函数**

把（第 192-229 行）：

```ts
// Loads every entity page for an @ mention category so the picker can expose all asset images.
async function listMentionEntities(entityType: MentionAssetKind): Promise<MentionEntityRecord[]> {
  const result: MentionEntityRecord[] = []
  let page = 1
  let maxPage = 1
  do {
    const res = await StudioEntitiesService.listEntitiesApiV1StudioEntitiesEntityTypeGet({
      entityType,
      page,
      pageSize: ASSET_MENTION_PAGE_SIZE,
    })
    const data = res.data
    result.push(...((data?.items ?? []) as MentionEntityRecord[]))
    maxPage = data?.pagination?.max_page ?? page
    page += 1
  } while (page <= maxPage)
  return result
}

// Loads every image page for one asset entity, keeping only records that have file_id.
async function listMentionEntityImages(entityType: MentionAssetKind, entityId: string): Promise<MentionImageRecord[]> {
  const result: MentionImageRecord[] = []
  let page = 1
  let maxPage = 1
  do {
    const res = await StudioEntitiesService.listEntityImagesApiV1StudioEntitiesEntityTypeEntityIdImagesGet({
      entityType,
      entityId,
      page,
      pageSize: ASSET_MENTION_PAGE_SIZE,
    })
    const data = res.data
    result.push(...((data?.items ?? []) as MentionImageRecord[]).filter((item) => Boolean(item.file_id)))
    maxPage = data?.pagination?.max_page ?? page
    page += 1
  } while (page <= maxPage)
  return result
}
```

删除。

- [ ] **Step 4b: 移除现在不再使用的 `StudioEntitiesService` import**

Step 4 删除后，`StudioEntitiesService` 在本文件里不再有任何引用（原来只被 `listMentionEntities`/`listMentionEntityImages` 使用），而 `front/tsconfig.json` 开启了 `noUnusedLocals: true`，留着会导致 `tsc --noEmit` 报错。

把（第 20 行）：

```ts
import { FilmService, LlmService, ScriptProcessingService, StudioEntitiesService, StudioFilesService } from '../../../../services/generated'
```

替换为：

```ts
import { FilmService, LlmService, ScriptProcessingService, StudioFilesService } from '../../../../services/generated'
```

- [ ] **Step 5: 删除 `mentionedFileIds` state**

把（第 286 行）：

```ts
  const [mentionedFileIds, setMentionedFileIds] = useState<string[]>([])
```

删除。

- [ ] **Step 6: 删除 `loadMentionImagesByKind` 回调**

把（第 857-878 行）：

```ts
  // Loads all reusable asset images for the selected @ mention category and deduplicates by file_id.
  const loadMentionImagesByKind = useCallback(async (kind: MentionAssetKind): Promise<MentionImageOption[]> => {
    const entities = await listMentionEntities(kind)
    const seen = new Set<string>()
    const options: MentionImageOption[] = []
    for (const entity of entities) {
      if (!entity.id) continue
      const entityName = entity.name || entity.title || entity.id
      const entityImages = await listMentionEntityImages(kind, entity.id)
      entityImages.forEach((image, index) => {
        if (!image.file_id || seen.has(image.file_id)) return
        seen.add(image.file_id)
        options.push({
          id: `${kind}:${entity.id}:${image.id ?? index}`,
          file_id: image.file_id,
          label: entityName,
          subtitle: image.name || entityName,
        })
      })
    }
    return options
  }, [])
```

删除。

- [ ] **Step 7: 把描述框从 `MentionEditor` 换成普通 `Input.TextArea`**

把（原第 958-967 行）：

```tsx
                  <MentionEditor
                    value={formDesc}
                    onChange={(text, fileIds) => {
                      setFormDesc(text)
                      setMentionedFileIds(fileIds)
                    }}
                    disabled={smartDetectBusy || savingBase}
                    placeholder="支持输入 @ 选择资产图片作为参考"
                    loadImagesByKind={loadMentionImagesByKind}
                  />
```

替换为：

```tsx
                  <Input.TextArea
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                    disabled={smartDetectBusy || savingBase}
                    placeholder="请输入描述"
                    autoSize={{ minRows: 4 }}
                  />
```

- [ ] **Step 8: 运行 typecheck，此时应报 `mentionedFileIds`/`images: mentionedFileIds` 相关错误（预期，Task 9/10 会消费新的参考图 state 修复）**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 报错定位在 `handleGenerateImage` 里 `images: mentionedFileIds`（`mentionedFileIds` 未定义），属预期中间态，Task 10 会修复

- [ ] **Step 9: Commit**

```bash
git add front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx
git commit -m "refactor: 移除资产编辑页描述框里的 @ 提及融图机制"
```

---

### Task 9: 接入参考图 state 与选图抽屉

**Files:**
- Modify: `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`

- [ ] **Step 1: 新增 import**

在 `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx` 顶部 import 区（紧跟 `DisplayImageCard` 的 import 之后，即原第 26 行之后）新增：

```ts
import { AssetReferencePickerDrawer, type AssetReferenceKind, type AssetReferenceOption } from './AssetReferencePickerDrawer'
import { AssetReferencePanel } from './AssetReferencePanel'
```

- [ ] **Step 2: 新增参考图相关 state**

紧跟在原 `mentionedFileIds` state 所在位置（现在应为 Task 8 删除后 `uploadingCandidates` state 之后、`assetImageResolutionProfile` state 之前，即原第 285-288 行附近）新增：

```ts
  const [referenceOptions, setReferenceOptions] = useState<AssetReferenceOption[]>([])
  const [referenceFileIds, setReferenceFileIds] = useState<string[]>([])
  const [referencePickerOpen, setReferencePickerOpen] = useState(false)
  const [referencePickerInitialKind, setReferencePickerInitialKind] = useState<AssetReferenceKind>('scene')
  const [referenceReplaceFileId, setReferenceReplaceFileId] = useState<string | null>(null)
```

- [ ] **Step 3: 新增打开抽屉 / 选图回调**

在 `handleCandidateUpload` 函数之后（原第 855-856 行附近，Task 8 删除 `loadMentionImagesByKind` 后这里会紧接 `if (!assetId)` 判空块之前）新增：

```ts
  // 打开资产库抽屉以"新增"一张参考图。
  const openReferencePickerToAdd = useCallback(() => {
    setReferencePickerInitialKind('scene')
    setReferenceReplaceFileId(null)
    setReferencePickerOpen(true)
  }, [])

  // 打开资产库抽屉以"替换"已选参考图列表里的某一项；按 fileId 反查其所属资产类型作为默认 tab。
  const openReferencePickerToReplace = useCallback(
    (fileId: string) => {
      const existing = referenceOptions.find((option) => option.file_id === fileId)
      setReferencePickerInitialKind(existing?.kind ?? 'scene')
      setReferenceReplaceFileId(fileId)
      setReferencePickerOpen(true)
    },
    [referenceOptions],
  )

  /**
   * 资产库选图确认回调：只把选中的资产图片临时加入本次生成的参考图候选，
   * 不写入任何资产关联关系——与镜头详情页关键帧生成的"临时参考图"语义一致。
   */
  const handleReferencePicked = useCallback(
    (option: AssetReferenceOption) => {
      setReferenceOptions((prev) => {
        const withoutDuplicate = prev.filter((item) => item.file_id !== option.file_id)
        return [...withoutDuplicate, option]
      })
      if (referenceReplaceFileId) {
        setReferenceFileIds((prev) => prev.map((id) => (id === referenceReplaceFileId ? option.file_id : id)))
      } else {
        setReferenceFileIds((prev) => (prev.includes(option.file_id) ? prev : [...prev, option.file_id]))
      }
      setReferencePickerOpen(false)
    },
    [referenceReplaceFileId],
  )
```

- [ ] **Step 4: 在描述框下方渲染 `AssetReferencePanel`**

把 Task 8 Step 7 替换后的这段：

```tsx
                  <Input.TextArea
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                    disabled={smartDetectBusy || savingBase}
                    placeholder="请输入描述"
                    autoSize={{ minRows: 4 }}
                  />
```

替换为：

```tsx
                  <Input.TextArea
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                    disabled={smartDetectBusy || savingBase}
                    placeholder="请输入描述"
                    autoSize={{ minRows: 4 }}
                  />
                  <div className="mt-3">
                    <AssetReferencePanel
                      options={referenceOptions}
                      selectedFileIds={referenceFileIds}
                      onChangeSelectedFileIds={setReferenceFileIds}
                      onAddFromLibrary={openReferencePickerToAdd}
                      onReplaceFromLibrary={openReferencePickerToReplace}
                      disabled={smartDetectBusy || savingBase}
                    />
                  </div>
```

- [ ] **Step 5: 渲染 `AssetReferencePickerDrawer`**

在文件末尾"智能检测：缺失信息" `Modal` 结束标签之后、组件 return 的最外层 `</div>` 之前（原第 1184-1186 行附近）新增：

```tsx
      <AssetReferencePickerDrawer
        open={referencePickerOpen}
        initialKind={referencePickerInitialKind}
        onSelect={handleReferencePicked}
        onClose={() => setReferencePickerOpen(false)}
      />
```

- [ ] **Step 6: 运行 typecheck**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: `mentionedFileIds` 相关错误仍在（Task 10 修复），本任务新增代码本身不应引入新的类型错误

- [ ] **Step 7: Commit**

```bash
git add front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx
git commit -m "feat: 资产编辑页接入参考图 state 与资产库选图抽屉"
```

---

### Task 10: 生成流程改为"预览确认后再生成"

**Files:**
- Modify: `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`

- [ ] **Step 1: 新增生成确认相关 state**

紧跟在 Task 9 Step 2 新增的参考图 state 之后新增：

```ts
  const [pendingGenerateImage, setPendingGenerateImage] = useState<TImage | null>(null)
  const [generateConfirmOpen, setGenerateConfirmOpen] = useState(false)
  const [generateConfirmLoading, setGenerateConfirmLoading] = useState(false)
  const [generateConfirmPrompt, setGenerateConfirmPrompt] = useState('')
  const [generateConfirmImages, setGenerateConfirmImages] = useState<string[]>([])
```

- [ ] **Step 2: 把 `handleGenerateImage` 拆成"预览"与"确认提交"两个函数**

把（原第 706-779 行）：

```ts
  // Saves current form edits and starts generation directly from the description field.
  const handleGenerateImage = async (image: TImage) => {
    if (!assetId || !asset) return
    const prompt = formDesc.trim()
    if (!prompt) {
      message.warning('请先填写描述')
      return
    }
    const payload = buildBasePayload()
    if (!payload) return

    setGeneratingByImageId((prev) => ({ ...prev, [image.id]: true }))
    setSavingBase(true)
    try {
      const nextAsset = await updateAsset(assetId, payload)
      if (nextAsset) setAsset(nextAsset)

      const taskId = await createGenerationTask(assetId, image.id, {
        prompt,
        images: mentionedFileIds,
        model_id: selectedImageModelId,
        quote_token: imageQuote.quoteToken,
        resolution_profile: assetImageResolutionProfile,
      })
      if (!taskId) {
        message.error('生成任务创建失败：缺少任务 ID')
        return
      }
      setGenerationTask({
        taskId,
        status: 'pending',
        progress: 0,
        cancelRequested: false,
      })
      setGenerationSettledTask(null)

      let finalStatus: TaskStatus = 'pending'
      let finalTaskState: RelationTaskState | null = null
      for (let i = 0; i < 30; i += 1) {
        await sleep(2000)
        const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
        const status = statusRes.data?.status
        if (!status) continue
        finalStatus = status
        if (statusRes.data) {
          finalTaskState = toRelationTaskStateFromStatusRead(statusRes.data)
          setGenerationTask(finalTaskState)
        }
        if (isTerminalStatus(status)) break
      }
      if (finalTaskState && isTerminalStatus(finalTaskState.status)) {
        setGenerationTask(null)
        setGenerationSettledTask(finalTaskState)
      }

      if (finalStatus === 'succeeded') {
        await loadData()
      } else if (finalStatus !== 'failed' && finalStatus !== 'cancelled') {
        message.warning('生成任务仍在执行，请稍后刷新')
      }
    } catch (error) {
      if (isAssetNameConflictError(error)) {
        message.error(`${assetDisplayName}名称已存在，请修改名称或编辑已有资产后再生成`)
      } else {
        // 优先识别积分业务错误（积分不足/报价已变更），命中后刷新报价并返回语义文案。
        const pointsAware = makePointsAwareGetErrorMessage(imageQuote.refresh)
        const msg = pointsAware(error, '发起生成失败')
        message.error(msg)
      }
    } finally {
      setSavingBase(false)
      setGeneratingByImageId((prev) => ({ ...prev, [image.id]: false }))
    }
  }
```

替换为：

```ts
  // Saves current form edits, fetches the rendered prompt+reference preview, and opens the
  // confirmation modal so users see exactly what will be sent before a billed generation starts.
  const openGenerateConfirm = async (image: TImage) => {
    if (!assetId || !asset) return
    const prompt = formDesc.trim()
    if (!prompt) {
      message.warning('请先填写描述')
      return
    }
    const payload = buildBasePayload()
    if (!payload) return

    setGeneratingByImageId((prev) => ({ ...prev, [image.id]: true }))
    setSavingBase(true)
    try {
      const nextAsset = await updateAsset(assetId, payload)
      if (nextAsset) setAsset(nextAsset)

      const rendered = await renderPromptPreview(assetId, image.id, {
        prompt,
        images: referenceFileIds,
      })
      setGenerateConfirmPrompt(rendered?.prompt ?? prompt)
      setGenerateConfirmImages(rendered?.images ?? referenceFileIds)
      setPendingGenerateImage(image)
      setGenerateConfirmOpen(true)
    } catch {
      message.error('生成预览失败')
    } finally {
      setSavingBase(false)
      setGeneratingByImageId((prev) => ({ ...prev, [image.id]: false }))
    }
  }

  // Runs the actual billed generation using the previewed prompt/images once the user confirms.
  const confirmGenerateImage = async () => {
    if (!assetId || !pendingGenerateImage) return
    const image = pendingGenerateImage
    setGenerateConfirmLoading(true)
    setGeneratingByImageId((prev) => ({ ...prev, [image.id]: true }))
    try {
      const taskId = await createGenerationTask(assetId, image.id, {
        prompt: generateConfirmPrompt,
        images: generateConfirmImages,
        model_id: selectedImageModelId,
        quote_token: imageQuote.quoteToken,
        resolution_profile: assetImageResolutionProfile,
      })
      if (!taskId) {
        message.error('生成任务创建失败：缺少任务 ID')
        return
      }
      setGenerateConfirmOpen(false)
      setPendingGenerateImage(null)
      setGenerationTask({
        taskId,
        status: 'pending',
        progress: 0,
        cancelRequested: false,
      })
      setGenerationSettledTask(null)

      let finalStatus: TaskStatus = 'pending'
      let finalTaskState: RelationTaskState | null = null
      for (let i = 0; i < 30; i += 1) {
        await sleep(2000)
        const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
        const status = statusRes.data?.status
        if (!status) continue
        finalStatus = status
        if (statusRes.data) {
          finalTaskState = toRelationTaskStateFromStatusRead(statusRes.data)
          setGenerationTask(finalTaskState)
        }
        if (isTerminalStatus(status)) break
      }
      if (finalTaskState && isTerminalStatus(finalTaskState.status)) {
        setGenerationTask(null)
        setGenerationSettledTask(finalTaskState)
      }

      if (finalStatus === 'succeeded') {
        await loadData()
      } else if (finalStatus !== 'failed' && finalStatus !== 'cancelled') {
        message.warning('生成任务仍在执行，请稍后刷新')
      }
    } catch (error) {
      if (isAssetNameConflictError(error)) {
        message.error(`${assetDisplayName}名称已存在，请修改名称或编辑已有资产后再生成`)
      } else {
        // 优先识别积分业务错误（积分不足/报价已变更），命中后刷新报价并返回语义文案。
        const pointsAware = makePointsAwareGetErrorMessage(imageQuote.refresh)
        const msg = pointsAware(error, '发起生成失败')
        message.error(msg)
      }
    } finally {
      setGenerateConfirmLoading(false)
      setGeneratingByImageId((prev) => ({ ...prev, [image.id]: false }))
    }
  }
```

- [ ] **Step 3: 把"生成"按钮的 `onClick` 从 `handleGenerateImage` 换成 `openGenerateConfirm`**

把（原第 1055 行）：

```tsx
                              onClick={() => slot.image && void handleGenerateImage(slot.image)}
```

替换为：

```tsx
                              onClick={() => slot.image && void openGenerateConfirm(slot.image)}
```

- [ ] **Step 4: 把 props 解构里加入 `renderPromptPreview`**

把组件函数签名（原第 231-247 行）：

```ts
export function AssetEditPageBase<TAsset extends BaseAsset, TImage extends BaseAssetImage>({
  assetId,
  missingAssetIdText,
  assetDisplayName,
  backTo,
  relationType,
  getAsset,
  updateAsset,
  listImages,
  createImageSlot,
  listImageCandidates,
  adoptImageCandidate,
  deleteImageCandidate,
  createGenerationTask,
  attachImageCandidates,
  onNavigate,
}: AssetEditPageBaseProps<TAsset, TImage>) {
```

替换为：

```ts
export function AssetEditPageBase<TAsset extends BaseAsset, TImage extends BaseAssetImage>({
  assetId,
  missingAssetIdText,
  assetDisplayName,
  backTo,
  relationType,
  getAsset,
  updateAsset,
  listImages,
  createImageSlot,
  listImageCandidates,
  adoptImageCandidate,
  deleteImageCandidate,
  createGenerationTask,
  renderPromptPreview,
  attachImageCandidates,
  onNavigate,
}: AssetEditPageBaseProps<TAsset, TImage>) {
```

- [ ] **Step 5: 新增生成确认 `Modal`**

在"智能检测：缺失信息" `Modal` 结束标签之后、Task 9 Step 5 新增的 `<AssetReferencePickerDrawer .../>` 之前，新增：

```tsx
      <Modal
        title="确认生成"
        open={generateConfirmOpen}
        onCancel={() => {
          if (generateConfirmLoading) return
          setGenerateConfirmOpen(false)
          setPendingGenerateImage(null)
        }}
        footer={
          <Space>
            <Button
              disabled={generateConfirmLoading}
              onClick={() => {
                setGenerateConfirmOpen(false)
                setPendingGenerateImage(null)
              }}
            >
              取消
            </Button>
            <PointsCostButton
              type="primary"
              loading={generateConfirmLoading}
              disabled={!generateConfirmPrompt.trim()}
              quote={imageQuote.quote}
              quoteLoading={imageQuote.loading}
              quoteError={imageQuote.error}
              onClick={() => void confirmGenerateImage()}
            >
              确认生成
            </PointsCostButton>
          </Space>
        }
        destroyOnClose
        width={720}
      >
        <div className="space-y-3">
          <div>
            <div className="text-gray-600 text-sm mb-1">最终提示词</div>
            <Input.TextArea value={generateConfirmPrompt} readOnly autoSize={{ minRows: 3, maxRows: 8 }} />
          </div>
          <div>
            <div className="text-gray-600 text-sm mb-1">参考图（{generateConfirmImages.length}）</div>
            {generateConfirmImages.length === 0 ? (
              <div className="text-xs text-gray-400">无参考图，本次为纯文生图</div>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-1">
                {generateConfirmImages.map((fid, index) => (
                  <img
                    key={fid}
                    src={buildFileDownloadUrl(fid)}
                    alt={`参考图${index + 1}`}
                    className="h-16 w-16 shrink-0 rounded object-cover border border-slate-200"
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </Modal>
```

- [ ] **Step 6: 运行 typecheck 确认全部通过**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 无错误

- [ ] **Step 7: Commit**

```bash
git add front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx
git commit -m "feat: 资产图片生成改为先预览最终提示词与参考图再确认提交"
```

---

### Task 11: 删除废弃的 `MentionEditor` 组件

**Files:**
- Delete: `front/src/pages/aiStudio/assets/components/MentionEditor.tsx`

- [ ] **Step 1: 确认无其他引用**

Run: `cd front && grep -rn "MentionEditor" src`
Expected: 只剩 `MentionEditor.tsx` 自身的定义（无其他文件引用）

- [ ] **Step 2: 删除文件**

```bash
git rm front/src/pages/aiStudio/assets/components/MentionEditor.tsx
```

- [ ] **Step 3: 运行 typecheck 确认删除文件不影响构建**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: 删除已被参考图管理区块替代的 MentionEditor 组件"
```

---

### Task 12: 更新架构文档

**Files:**
- Modify: `site/content/docs/architecture/generation-workspace.md`

- [ ] **Step 1: 在"资产编辑页"小节末尾追加说明**

把（当前文件"资产编辑页"小节末尾这段）：

```markdown
当前资产图片生成提交也已统一为：

- 页面维护 `base + context`
- `submitNow()` 在提交前自动保证 `derived` 最新
- 任务创建使用最新的 `derived.prompt + derived.images`
- 调试信息默认收起，仅在用户主动展开时展示上下文与质量校验细节
```

替换为：

```markdown
当前资产图片生成提交也已统一为：

- 页面维护 `base + context`
- `submitNow()` 在提交前自动保证 `derived` 最新
- 任务创建使用最新的 `derived.prompt + derived.images`
- 调试信息默认收起，仅在用户主动展开时展示上下文与质量校验细节

资产编辑页的参考图来源已从描述框内的 `@` 提及机制迁移为独立的参考图管理区块：

- 用户可以从角色/演员/场景/道具/服装 5 种资产类型的资产库里选择其他资产的代表图作为参考图，支持拖拽排序、替换、移除。
- 参考图仅作为本次生成的临时候选，不写入任何资产关联关系，语义与镜头详情页关键帧生成的"临时参考图"一致。
- 生成前会调用 render-prompt 接口预览最终提示词与参考图组合，用户确认后才真正提交计费生成任务；render-prompt 接口已改为直接复用与提交任务相同的 `build_xxx_image_submission_payload` 逻辑，确保预览结果与实际生成完全一致。
```

- [ ] **Step 2: Commit**

```bash
git add site/content/docs/architecture/generation-workspace.md
git commit -m "docs: 记录资产编辑页参考图管理区块替代 @ 提及机制"
```

---

### Task 13: 前端浏览器手动验证

**Files:** 无代码改动，仅验证

- [ ] **Step 1: 启动前后端开发服务器**

Run: `cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`（后台运行）
Run: `cd front && pnpm dev`（后台运行）

- [ ] **Step 2: 验证角色资产编辑页参考图功能**

打开浏览器访问角色资产编辑页，依次验证：
1. 描述框是普通文本框，不再有 `@` 提及弹窗。
2. 点击"添加参考图"打开抽屉，可在角色/演员/场景/道具/服装 5 个 tab 间切换并搜索。
3. 选中一个有图片的其他资产后，抽屉关闭，参考图卡片出现在描述框下方。
4. 拖拽卡片可调整顺序；点击"替换"重新打开抽屉选新资产替换该位置；点击"移除"从列表删除。
5. 点击某个角度图片下的"生成"，弹出"确认生成"弹窗，展示的提示词文本与描述框内容一致，参考图缩略图与已选参考图一致。
6. 点击"确认生成"，生成任务正常创建并轮询直到完成，新图片出现在候选池里。
7. 清空描述后点击"生成"应直接提示"请先填写描述"，不打开确认弹窗；若通过预览打开了弹窗但描述随后被清空，"确认生成"按钮应保持置灰。
8. 选择一个没有可用图片的资产时，抽屉里点击"确认添加"后应提示"该资产暂无可用图片，无法作为参考图"且不关闭抽屉。

- [ ] **Step 3: 对场景/道具/服装/演员资产编辑页重复验证第 2 步的核心路径（添加参考图 + 生成 + 确认弹窗）**

Expected: 5 种资产类型行为一致，无 JS 报错（打开浏览器控制台确认无 console error）

- [ ] **Step 4: 停止开发服务器**

如果是后台启动的进程，验证完成后终止对应进程。
