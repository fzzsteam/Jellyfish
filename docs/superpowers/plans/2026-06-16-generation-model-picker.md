# Generation Model Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在分镜工作室的关键帧图片生成和视频生成面板中，添加可视化"选择模型"卡片选择器，让用户在触发生成前可选择具体模型（参考巨日禄风格的卡片宫格 UI），并将所选模型 ID 传入后端生成任务。

**Architecture:** 后端新增 `GET /api/v1/llm/models/picker` 接口，联表返回带 `provider_name` 和 `is_default` 的精简 Model 列表；视频生成请求体新增可选 `model_id` 字段（图片生成接口已有该字段）；前端新增 `ModelPickerGrid` 可视化组件和 `useGenerationModels` 数据 hook，在 ChapterStudio 的关键帧和视频生成面板中嵌入，选中的 model_id 随生成请求下发。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, React 18, TypeScript, Ant Design 5, OpenAPI generated client.

---

## 当前代码关键事实

- 图片生成任务：`ShotFrameImageTaskRequest`（`backend/app/api/v1/routes/studio/image_tasks.py:83`）已有 `model_id: str | None` 字段，但前端在三处均硬编码为 `null`（ChapterStudio.tsx:1368, 1544, 3460）。
- 视频生成请求：`VideoGenerationTaskRequest`（`backend/app/api/v1/routes/film/video_request.py`）**无** `model_id` 字段，服务层 `build_run_args()`（`backend/app/services/film/generated_video.py:147`）始终调用 `resolve_default_video_model(db)` 取全局默认。
- 视频生成路由处理函数：`backend/app/api/v1/routes/film/generated_video.py:56`，调用 `build_run_args(...)` 传入请求体字段，当前不传 model_id。
- 模型列表接口：已有 `GET /api/v1/llm/models?category=image|video`，但返回的 `ModelRead` 只含 `provider_id`，不含 `provider_name`，前端无法直接渲染供应商标签。
- 分镜工作室关键帧规格面板（ChapterStudio.tsx:4476）：显示"当前模型：供应商/模型名"的只读文本，无交互选择。
- 分镜工作室视频参数面板（ChapterStudio.tsx:4960）：已有一个写死 `model_a / model_b` 的 mock `<Select>` 占位器，应替换为真实模型卡片选择器。
- 当前唯一可用供应商：**阿里百炼（aliyun_bailian）**，图片模型 `wan2.7-image-pro`，视频模型 `happyhorse-1.0-t2v`。

---

## 文件结构

### Backend Create
- `backend/app/schemas/llm_picker.py`：新增 `ModelPickerItemRead` schema（id, name, description, provider_id, provider_name, is_default）。
- `backend/tests/test_llm_picker_api.py`：picker 接口单测。

### Backend Modify
- `backend/app/api/v1/routes/film/video_request.py`：新增 `model_id: str | None` 字段。
- `backend/app/services/film/generated_video.py`：`build_run_args()` 新增 `model_id` 参数，按需跳过默认模型查询。
- `backend/app/api/v1/routes/film/generated_video.py`：路由处理函数传 `model_id=body.model_id`。
- `backend/app/api/v1/routes/llm.py`：新增 `/models/picker` 接口。
- `backend/app/services/llm/manage.py`：新增 `list_models_for_picker()` 服务函数。

### Frontend Create
- `front/src/pages/aiStudio/chapter/hooks/useGenerationModels.ts`：按类别拉取可用模型列表。
- `front/src/pages/aiStudio/chapter/components/ModelPickerGrid.tsx`：可视化模型卡片宫格组件。

### Frontend Modify
- `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`：
  - 增加 `selectedImageModelId` / `selectedVideoModelId` 状态；
  - 关键帧规格面板嵌入 `ModelPickerGrid`（替换只读文本）；
  - 视频参数面板嵌入 `ModelPickerGrid`（替换 mock Select）；
  - 三处 `model_id: null` 改为 `model_id: selectedImageModelId`；
  - 视频生成调用增加 `model_id: selectedVideoModelId`。
- `front/openapi.json` + `front/src/services/generated/`：运行 `openapi:update` 后自动更新。

---

## Task 1：后端 —— `VideoGenerationTaskRequest` 新增 `model_id`

**Files:**
- Modify: `backend/app/api/v1/routes/film/video_request.py`

- [ ] **Step 1.1：增加 `model_id` 字段**

替换文件内容为：

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from app.core.contracts.video_generation import VideoRatio

class VideoGenerationTaskRequest(BaseModel):
    """视频生成任务请求。"""

    shot_id: str = Field(..., description="镜头 ID")
    reference_mode: Literal["first", "last", "key", "first_last", "first_last_key", "text_only"] = Field(
        ...,
        description="参考模式：first | last | key | first_last | first_last_key | text_only",
    )
    prompt: str | None = Field(None, description="视频提示词（text_only 必填）")
    images: list[str] = Field(
        default_factory=list,
        description="参考图 file_id 列表，数量需与 reference_mode 严格匹配",
    )
    ratio: VideoRatio = Field(..., description="视频画幅比例，如 16:9 / 9:16")
    model_id: str | None = Field(None, description="指定视频模型 ID（models.id）；不传则使用 ModelSettings.default_video_model_id")
```

- [ ] **Step 1.2：语法检查**

```bash
cd backend
python -m py_compile app/api/v1/routes/film/video_request.py
```

期望输出：无错误

- [ ] **Step 1.3：commit**

```bash
git add backend/app/api/v1/routes/film/video_request.py
git commit -m "feat: add model_id to VideoGenerationTaskRequest"
```

---

## Task 2：后端 —— 视频生成服务支持显式 `model_id`

**Files:**
- Modify: `backend/app/services/film/generated_video.py`（`resolve_default_video_model` → `resolve_video_model`，`build_run_args` 新增参数）
- Modify: `backend/app/api/v1/routes/film/generated_video.py`（路由传 model_id）

- [ ] **Step 2.1：`generated_video.py` 新增 `resolve_video_model()` 并更新 `build_run_args()`**

在 `backend/app/services/film/generated_video.py` 中：

将 `resolve_default_video_model` 函数之后（约第 120 行），新增辅助函数：

```python
async def resolve_video_model(db: AsyncSession, *, model_id: str | None = None) -> Model:
    """按 model_id 解析视频模型；未指定时回退到全局默认。"""
    if model_id:
        model = await db.get(Model, model_id)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Specified video model not found: {model_id}")
        if model.category != ModelCategoryKey.video:
            raise HTTPException(
                status_code=400,
                detail=f"Specified model is not video category: {model_id} (category={model.category})",
            )
        return model
    return await resolve_default_video_model(db)
```

然后将 `build_run_args()` 函数签名（约第 147 行）更新为：

```python
async def build_run_args(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    prompt: str | None,
    images: list[str],
    ratio: str | None,
    model_id: str | None = None,
) -> dict:
    model = await resolve_video_model(db, model_id=model_id)
    # 以下保持不变...
```

（`model = await resolve_default_video_model(db)` 这一行改为 `model = await resolve_video_model(db, model_id=model_id)`）

- [ ] **Step 2.2：更新路由处理函数**

在 `backend/app/api/v1/routes/film/generated_video.py` 的 `create_video_generation_task` 函数（约第 64 行），将 `build_run_args(...)` 调用改为：

```python
    run_args = await build_run_args(
        db,
        shot_id=body.shot_id,
        reference_mode=body.reference_mode,
        prompt=body.prompt,
        images=body.images,
        ratio=body.ratio,
        model_id=body.model_id,
    )
```

- [ ] **Step 2.3：语法检查**

```bash
cd backend
python -m py_compile app/services/film/generated_video.py app/api/v1/routes/film/generated_video.py
```

期望输出：无错误

- [ ] **Step 2.4：运行相关测试**

```bash
cd backend
uv run pytest tests/test_generated_video_service.py -q
```

期望输出：所有已有测试继续通过（新增字段有默认值 `None`，不影响已有测试用例）

- [ ] **Step 2.5：commit**

```bash
git add backend/app/services/film/generated_video.py backend/app/api/v1/routes/film/generated_video.py
git commit -m "feat: video generation service accepts explicit model_id"
```

---

## Task 3：后端 —— 新增模型选择器专用接口

**Files:**
- Create: `backend/app/schemas/llm_picker.py`
- Modify: `backend/app/services/llm/manage.py`（新增 `list_models_for_picker()`）
- Modify: `backend/app/api/v1/routes/llm.py`（注册 `/models/picker` 路由）
- Create: `backend/tests/test_llm_picker_api.py`

- [ ] **Step 3.1：创建 `llm_picker.py` schema**

```python
# backend/app/schemas/llm_picker.py
"""模型选择器专用 Schema（联表展示供应商信息）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelPickerItemRead(BaseModel):
    """模型选择器列表项：含供应商名称与是否为默认模型。"""

    id: str = Field(..., description="模型 ID（models.id）")
    name: str = Field(..., description="模型名称")
    description: str = Field("", description="模型说明")
    provider_id: str = Field(..., description="所属供应商 ID")
    provider_name: str = Field(..., description="供应商展示名")
    is_default: bool = Field(False, description="是否为当前类别的全局默认模型")
```

- [ ] **Step 3.2：新增测试（先写失败测试）**

创建 `backend/tests/test_llm_picker_api.py`：

```python
"""模型选择器接口响应测试。"""
from __future__ import annotations

import pytest

from app.models.llm import ModelCategoryKey, ModelSettings, Provider, Model


class _FakeDB:
    def __init__(self):
        self.providers: dict[str, Provider] = {}
        self.models: dict[str, Model] = {}
        self.model_settings: dict[int, ModelSettings] = {}

    async def get(self, cls, pk):
        if cls == ModelSettings:
            return self.model_settings.get(pk)
        return None

    async def execute(self, stmt):
        # 简化 scalars：返回 FakeResult
        return _FakeResult(list(self.models.values()))


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


def _seed(db: _FakeDB) -> None:
    p = Provider(id="p-bailian", name="阿里百炼", base_url="https://dashscope.aliyuncs.com", api_key="k")
    db.providers["p-bailian"] = p
    m_img = Model(id="m-img", name="wan2.7-image-pro", category=ModelCategoryKey.image, provider_id="p-bailian")
    m_vid = Model(id="m-vid", name="happyhorse-1.0-t2v", category=ModelCategoryKey.video, provider_id="p-bailian")
    db.models["m-img"] = m_img
    db.models["m-vid"] = m_vid
    db.model_settings[1] = ModelSettings(id=1, default_image_model_id="m-img", default_video_model_id="m-vid")


@pytest.mark.asyncio
async def test_list_models_for_picker_image_category():
    from app.services.llm.manage import list_models_for_picker

    db = _FakeDB()
    _seed(db)
    items = await list_models_for_picker(db, category=ModelCategoryKey.image)
    assert len(items) == 1
    item = items[0]
    assert item.id == "m-img"
    assert item.provider_name == "阿里百炼"
    assert item.is_default is True


@pytest.mark.asyncio
async def test_list_models_for_picker_video_category():
    from app.services.llm.manage import list_models_for_picker

    db = _FakeDB()
    _seed(db)
    items = await list_models_for_picker(db, category=ModelCategoryKey.video)
    assert len(items) == 1
    item = items[0]
    assert item.id == "m-vid"
    assert item.is_default is True
```

- [ ] **Step 3.3：运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_llm_picker_api.py -q
```

期望输出：ImportError 或 AttributeError（`list_models_for_picker` 还不存在）

- [ ] **Step 3.4：在 `manage.py` 新增 `list_models_for_picker()`**

在 `backend/app/services/llm/manage.py` 末尾追加：

```python
from sqlalchemy import select as sa_select

async def list_models_for_picker(
    db: AsyncSession,
    *,
    category: ModelCategoryKey,
) -> list["ModelPickerItemRead"]:
    """按类别返回模型选择器列表（含供应商名称与默认标记）。"""
    from app.schemas.llm_picker import ModelPickerItemRead

    # 查询指定类别的所有模型
    stmt = sa_select(Model).where(Model.category == category).order_by(Model.name)
    result = await db.execute(stmt)
    models = result.scalars().all()

    if not models:
        return []

    # 批量拉取供应商（避免 N+1）
    provider_ids = list({m.provider_id for m in models})
    prov_stmt = sa_select(Provider).where(Provider.id.in_(provider_ids))
    prov_result = await db.execute(prov_stmt)
    provider_map: dict[str, str] = {p.id: p.name for p in prov_result.scalars().all()}

    # 确定默认模型 ID
    settings = await db.get(ModelSettings, 1)
    default_id = (
        settings.default_image_model_id
        if category == ModelCategoryKey.image
        else settings.default_video_model_id
        if settings
        else None
    )

    return [
        ModelPickerItemRead(
            id=m.id,
            name=m.name,
            description=m.description or "",
            provider_id=m.provider_id,
            provider_name=provider_map.get(m.provider_id, m.provider_id),
            is_default=(m.id == default_id),
        )
        for m in models
    ]
```

注意：需要在文件顶部已有 `from sqlalchemy import select` 时不重复导入；若文件中已有 `from sqlalchemy import select`，则使用相同 alias 或合并导入。

- [ ] **Step 3.5：在 `llm.py` 路由文件添加接口**

在 `backend/app/api/v1/routes/llm.py` 的 `list_supported_providers` 之后添加：

```python
from app.schemas.llm_picker import ModelPickerItemRead
from app.services.llm.manage import list_models_for_picker as list_models_for_picker_service

@router.get(
    "/models/picker",
    response_model=ApiResponse[list[ModelPickerItemRead]],
    summary="获取指定类别的模型列表（含供应商名称，用于前端选择器）",
)
async def list_models_for_picker(
    category: ModelCategoryKey = Query(..., description="模型类别：image / video"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ModelPickerItemRead]]:
    items = await list_models_for_picker_service(db, category=category)
    return success_response(items)
```

**重要**：此路由必须注册在 `/models/{model_id}` 之前，否则 FastAPI 会将 `picker` 解析为 model_id。检查 `llm.py` 中的路由顺序，确认 `/models/picker` 在 `/models/{model_id}` 之前定义。

- [ ] **Step 3.6：运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_llm_picker_api.py -q
```

期望输出：`2 passed`

- [ ] **Step 3.7：语法检查**

```bash
cd backend
python -m py_compile app/schemas/llm_picker.py app/services/llm/manage.py app/api/v1/routes/llm.py
```

期望输出：无错误

- [ ] **Step 3.8：commit**

```bash
git add backend/app/schemas/llm_picker.py backend/app/services/llm/manage.py backend/app/api/v1/routes/llm.py backend/tests/test_llm_picker_api.py
git commit -m "feat: add /api/v1/llm/models/picker endpoint for generation model selector"
```

---

## Task 4：前端 —— 同步 OpenAPI 生成客户端

**Files:**
- Modify: `front/openapi.json`
- Modify: `front/src/services/generated/` (全部自动更新)

前提：后端在 `http://127.0.0.1:8000` 运行。

- [ ] **Step 4.1：启动后端**

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 4.2：同步生成客户端**

```bash
cd front
pnpm run openapi:update
```

期望输出：`openapi.json` 更新，`src/services/generated/` 下新增或更新：
- `models/ModelPickerItemRead.ts`
- `services/LlmService.ts` 中新增 `listModelsForPickerApiV1LlmModelsPickerGet()`
- `models/VideoGenerationTaskRequest.ts` 中新增可选 `model_id` 字段

- [ ] **Step 4.3：typecheck 验证**

```bash
cd front
pnpm run typecheck
```

期望输出：无 TypeScript 错误

- [ ] **Step 4.4：commit**

```bash
git add front/openapi.json front/src/services/generated/
git commit -m "chore: sync openapi client for model picker and video model_id"
```

---

## Task 5：前端 —— `useGenerationModels` 数据 hook

**Files:**
- Create: `front/src/pages/aiStudio/chapter/hooks/useGenerationModels.ts`

- [ ] **Step 5.1：创建 hook 文件**

```typescript
// front/src/pages/aiStudio/chapter/hooks/useGenerationModels.ts
import { useEffect, useState } from 'react'
import { LlmService } from '../../../../services/generated'
import type { ModelPickerItemRead } from '../../../../services/generated'

export type GenerationCategory = 'image' | 'video'

export type UseGenerationModelsResult = {
  models: ModelPickerItemRead[]
  loading: boolean
  defaultModelId: string | null
}

/**
 * 按生成类别（image / video）拉取当前系统配置的可用模型列表。
 * 返回模型列表、加载状态和默认模型 ID。
 */
export function useGenerationModels(category: GenerationCategory): UseGenerationModelsResult {
  const [models, setModels] = useState<ModelPickerItemRead[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    void LlmService.listModelsForPickerApiV1LlmModelsPickerGet({ category })
      .then((res) => {
        if (!active) return
        setModels(res.data ?? [])
      })
      .catch(() => {
        if (!active) return
        setModels([])
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [category])

  const defaultModelId = models.find((m) => m.is_default)?.id ?? null

  return { models, loading, defaultModelId }
}
```

- [ ] **Step 5.2：typecheck 验证**

```bash
cd front
pnpm run typecheck
```

期望输出：无错误

- [ ] **Step 5.3：commit**

```bash
git add front/src/pages/aiStudio/chapter/hooks/useGenerationModels.ts
git commit -m "feat: add useGenerationModels hook for image/video model picker"
```

---

## Task 6：前端 —— `ModelPickerGrid` 组件

**Files:**
- Create: `front/src/pages/aiStudio/chapter/components/ModelPickerGrid.tsx`

视觉要求：参考巨日禄截图风格
- 卡片宫格（`grid grid-cols-2` 或 `3`），暗色风格
- 每张卡显示：供应商标签（彩色 Tag）、模型名称（粗体）、简短描述
- 选中态：蓝色描边 + 轻微背景色
- 默认模型徽章：右上角小橙色 "默认" Tag

- [ ] **Step 6.1：创建组件**

```tsx
// front/src/pages/aiStudio/chapter/components/ModelPickerGrid.tsx
import React from 'react'
import { Spin, Tag, Tooltip } from 'antd'
import { CheckCircleFilled } from '@ant-design/icons'
import type { ModelPickerItemRead } from '../../../../services/generated'

/** 供应商 key → 展示颜色映射 */
const PROVIDER_COLOR: Record<string, string> = {
  aliyun_bailian: 'orange',
  openai: 'green',
  volcengine: 'blue',
  vidu: 'purple',
}

function providerColor(providerId: string): string {
  const key = Object.keys(PROVIDER_COLOR).find((k) => providerId.toLowerCase().includes(k))
  return key ? PROVIDER_COLOR[key] : 'default'
}

type ModelPickerGridProps = {
  models: ModelPickerItemRead[]
  loading: boolean
  /** 当前选中的模型 ID；null 表示使用默认 */
  selectedId: string | null
  onChange: (modelId: string | null) => void
  /** 可选说明文案 */
  hint?: string
}

/**
 * 可视化模型选择器卡片宫格。
 * 选中 null 时表示使用系统默认模型。
 */
export const ModelPickerGrid: React.FC<ModelPickerGridProps> = ({
  models,
  loading,
  selectedId,
  onChange,
  hint,
}) => {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Spin size="small" />
      </div>
    )
  }

  if (models.length === 0) {
    return (
      <div className="rounded border border-dashed border-gray-200 py-3 text-center text-xs text-gray-400">
        未配置可用模型，请前往「模型管理」添加
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {hint && <div className="text-xs text-gray-400">{hint}</div>}
      <div className="grid grid-cols-2 gap-2">
        {models.map((model) => {
          const isSelected = selectedId === model.id
          return (
            <Tooltip key={model.id} title={model.description || model.name} placement="top">
              <div
                role="button"
                tabIndex={0}
                onClick={() => onChange(isSelected ? null : model.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') onChange(isSelected ? null : model.id)
                }}
                className={[
                  'relative cursor-pointer rounded-lg border p-2.5 transition-all select-none',
                  isSelected
                    ? 'border-blue-500 bg-blue-50 shadow-sm'
                    : 'border-gray-200 bg-gray-50 hover:border-blue-300 hover:bg-blue-50/30',
                ].join(' ')}
              >
                {/* 默认徽章 */}
                {model.is_default && (
                  <div className="absolute right-1.5 top-1.5">
                    <Tag color="orange" className="text-[10px] leading-4 px-1 py-0 m-0">默认</Tag>
                  </div>
                )}
                {/* 选中勾 */}
                {isSelected && (
                  <div className="absolute left-1.5 top-1.5 text-blue-500">
                    <CheckCircleFilled style={{ fontSize: 12 }} />
                  </div>
                )}
                {/* 供应商标签 */}
                <div className="mb-1">
                  <Tag color={providerColor(model.provider_id)} className="text-[10px] leading-4 px-1.5 py-0 m-0">
                    {model.provider_name}
                  </Tag>
                </div>
                {/* 模型名 */}
                <div className="text-xs font-medium text-gray-800 leading-tight line-clamp-2">
                  {model.name}
                </div>
              </div>
            </Tooltip>
          )
        })}
      </div>
      {selectedId === null && (
        <div className="text-xs text-gray-400">
          未选择时自动使用系统默认模型
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 6.2：typecheck 验证**

```bash
cd front
pnpm run typecheck
```

期望输出：无错误

- [ ] **Step 6.3：commit**

```bash
git add front/src/pages/aiStudio/chapter/components/ModelPickerGrid.tsx
git commit -m "feat: add ModelPickerGrid visual model selector component"
```

---

## Task 7：前端 —— ChapterStudio 集成图片模型选择

**Files:**
- Modify: `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`

本任务处理**图片生成**（关键帧）的模型选择集成。

- [ ] **Step 7.1：在组件顶部导入新 hook 和组件**

在 `ChapterStudio.tsx` 的 import 区域，追加（在现有 import 之后）：

```tsx
import { useGenerationModels } from '../hooks/useGenerationModels'
import { ModelPickerGrid } from './components/ModelPickerGrid'
```

- [ ] **Step 7.2：在组件函数体中添加图片模型 hook 和状态**

在 `ChapterStudio` 组件函数内（`const { projectId, chapterId } = useParams(...)` 之后），添加：

```tsx
// 图片模型选择
const { models: imageModels, loading: imageModelsLoading } = useGenerationModels('image')
const [selectedImageModelId, setSelectedImageModelId] = useState<string | null>(null)
```

- [ ] **Step 7.3：关键帧规格面板嵌入模型选择器**

找到 ChapterStudio.tsx 约第 4476 行的 `keyframe_gen` tab 内容，定位到如下代码块（约 4496～4507 行）：

```tsx
                    <div className="mt-2 rounded bg-gray-50 px-3 py-2 text-xs text-gray-600">
                      <div>
                        当前规格：{resolvedKeyframeRatio || '未设置比例'} ·{' '}
                        {getResolutionProfileLabel(keyframeResolutionProfile)}
                        {resolvedKeyframePixelSize ? ` → ${resolvedKeyframePixelSize}` : ''}
                      </div>
                      <div className="mt-1 text-gray-500">
                        当前模型：{imageGenerationOptions?.provider || '未识别供应商'}
                        {imageGenerationOptions?.model_name ? ` / ${imageGenerationOptions.model_name}` : ''}
                      </div>
                    </div>
```

将其替换为：

```tsx
                    <div className="mt-2 rounded bg-gray-50 px-3 py-2 text-xs text-gray-600">
                      <div>
                        当前规格：{resolvedKeyframeRatio || '未设置比例'} ·{' '}
                        {getResolutionProfileLabel(keyframeResolutionProfile)}
                        {resolvedKeyframePixelSize ? ` → ${resolvedKeyframePixelSize}` : ''}
                      </div>
                    </div>
                    <div className="mt-3">
                      <div className="mb-1.5 text-xs font-medium text-gray-600">选择图片模型</div>
                      <ModelPickerGrid
                        models={imageModels}
                        loading={imageModelsLoading}
                        selectedId={selectedImageModelId}
                        onChange={setSelectedImageModelId}
                        hint="不选则使用系统默认图片模型"
                      />
                    </div>
```

- [ ] **Step 7.4：三处 `model_id: null` 改为传 `selectedImageModelId`**

1. **第 1368 行**（`runBatchGenerate` 中的 `createShotFrameImageGenerationTask` 调用）：

   将：
   ```tsx
               model_id: null,
   ```
   改为：
   ```tsx
               model_id: selectedImageModelId,
   ```

2. **第 1544 行**（`generateFrameImageTask` 中）：

   将：
   ```tsx
         model_id: null,
   ```
   改为：
   ```tsx
         model_id: selectedImageModelId,
   ```

3. **第 3460 行**（`generateKeyframeCard` 中，批量关键帧生成函数）：

   将：
   ```tsx
             model_id: null,
   ```
   改为：
   ```tsx
             model_id: selectedImageModelId,
   ```

- [ ] **Step 7.5：typecheck 验证**

```bash
cd front
pnpm run typecheck
```

期望输出：无错误

- [ ] **Step 7.6：commit**

```bash
git add front/src/pages/aiStudio/chapter/ChapterStudio.tsx
git commit -m "feat: add image model picker to keyframe generation panel"
```

---

## Task 8：前端 —— ChapterStudio 视频生成面板改造

**背景变更（相对初始计划）：**
- "参考"一栏（关键帧类型选择器，4942–4956 行）**整体删除**，视频生成固定走 `text_only` 文生视频模式
- "参数"一栏（mock ControlNet/Slider，4958–4978 行）**整体删除**
- "生成"一栏（4981–4991 行）**新增"选择模型"按钮**：点击弹出 Popover，列出所有已配置的视频模型供选择
- `noUnusedLocals: true` 严格开启，需同步删除仅服务于已删 UI 的状态声明

**Files:**
- Modify: `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`

---

- [ ] **Step 8.1：添加视频模型 hook 和状态**

在 Task 7.2 添加的状态之后，紧接着追加：

```tsx
// 视频模型选择（文生视频）
const { models: videoModels, loading: videoModelsLoading } = useGenerationModels('video')
const [selectedVideoModelId, setSelectedVideoModelId] = useState<string | null>(null)
const [videoModelPickerOpen, setVideoModelPickerOpen] = useState(false)
```

---

- [ ] **Step 8.2：删除"参考"相关状态声明和辅助函数**

以下状态/函数全部由"参考"UI 驱动，删除后避免 `noUnusedLocals` 报错。

**删除 2712–2714 行的三行声明**（状态声明区）：

```tsx
  const [refImageType, setRefImageType] = useState<string | undefined>(undefined)
  const [refFrameTypeSelectLoading, setRefFrameTypeSelectLoading] = useState(false)
  const [useBoneDepth, setUseBoneDepth] = useState(false)
```

**删除 2955 行的单行声明**：

```tsx
  const showGenRefParams = false
```

**删除 3813–3824 行 `handleRefFrameTypeDropdownVisibleChange` 函数**：

```tsx
  const handleRefFrameTypeDropdownVisibleChange = useCallback(
    async (open: boolean) => {
      if (!open || !onRefreshShotFrameImages) return
      setRefFrameTypeSelectLoading(true)
      try {
        await onRefreshShotFrameImages()
      } finally {
        setRefFrameTypeSelectLoading(false)
      }
    },
    [onRefreshShotFrameImages],
  )
```

**删除 3826–3834 行 `refFrameTypeOptions` useMemo**：

```tsx
  const refFrameTypeOptions = useMemo(() => {
    const kinds = new Set((frameImages ?? []).map((x) => x.frame_type))
    const opts: Array<{ value: string; label: string }> = []
    if (kinds.has('first')) opts.push({ value: 'first', label: '首帧' })
    if (kinds.has('last')) opts.push({ value: 'last', label: '尾帧' })
    if (kinds.has('first') && kinds.has('last')) opts.push({ value: 'first_last', label: '首尾帧' })
    if (kinds.has('key')) opts.push({ value: 'key', label: '关键帧' })
    return opts
  }, [frameImages])
```

**删除 3836–3839 行的 useEffect**（依赖 refFrameTypeOptions/setRefImageType）：

```tsx
  useEffect(() => {
    const allowed = new Set(refFrameTypeOptions.map((x) => x.value))
    setRefImageType((prev) => (prev && allowed.has(prev) ? prev : undefined))
  }, [refFrameTypeOptions])
```

**删除 3841–3857 行 `buildVideoRefSelection` 函数**：

```tsx
  const buildVideoRefSelection = () => {
    const first = frameImages.find((x) => x.frame_type === 'first')?.file_id ?? null
    const last = frameImages.find((x) => x.frame_type === 'last')?.file_id ?? null
    const key = frameImages.find((x) => x.frame_type === 'key')?.file_id ?? null

    const s = refImageType
    if (s === 'first_last') {
      return {
        referenceMode: 'first_last' as const,
        images: [first, last].filter((x): x is string => Boolean(x)),
      }
    }
    if (s === 'key') return { referenceMode: 'key' as const, images: key ? [key] : [] }
    if (s === 'first') return { referenceMode: 'first' as const, images: first ? [first] : [] }
    if (s === 'last') return { referenceMode: 'last' as const, images: last ? [last] : [] }
    return { referenceMode: 'text_only' as const, images: [] }
  }
```

---

- [ ] **Step 8.3：内联 `buildVideoRefSelection()` 调用改为 text_only**

找到 `openVideoPromptPreview` 函数（约 3859 行），将：

```tsx
    const { referenceMode, images } = buildVideoRefSelection()
    const nextContext = { referenceMode, images }
    videoPromptDraft.hydrate({
      base: { prompt: '' },
      context: nextContext,
    })
```

替换为：

```tsx
    const nextContext = { referenceMode: 'text_only' as const, images: [] as string[] }
    videoPromptDraft.hydrate({
      base: { prompt: '' },
      context: nextContext,
    })
```

同一函数内 `referenceMode` 被另外引用的地方（约第 3882 行）：

```tsx
        videoPromptDraft.hydrate({
          base: { prompt: derived.prompt },
          context: {
            referenceMode,
            images: derived.images,
          },
          derived,
        })
```

替换为：

```tsx
        videoPromptDraft.hydrate({
          base: { prompt: derived.prompt },
          context: {
            referenceMode: 'text_only' as const,
            images: derived.images,
          },
          derived,
        })
```

---

- [ ] **Step 8.4：删除 gen_ref tab 内的"参考"和"参数"UI 区块**

找到 gen_ref tab 内容（约 4942–4978 行），删除以下两个 `cs-group` div：

```tsx
                  <div className="cs-group">
                    <div className="cs-group-title">
                      <LinkOutlined /> 参考
                    </div>
                    <Select
                      allowClear
                      placeholder="按已有关键帧类型选择"
                      className="w-full"
                      value={refImageType}
                      onChange={(v) => setRefImageType(v === undefined || v === null ? undefined : String(v))}
                      options={refFrameTypeOptions}
                      loading={refFrameTypeSelectLoading}
                      onDropdownVisibleChange={handleRefFrameTypeDropdownVisibleChange}
                    />
                  </div>

                  {showGenRefParams && (
                    <div className="cs-group">
                      <div className="cs-group-title">
                        <ToolOutlined /> 参数
                      </div>
                      <Space direction="vertical" className="w-full" size="small">
                        <Select
                          size="small"
                          placeholder="模型选择"
                          options={[
                            { value: 'model_a', label: '模型 A（写实）' },
                            { value: 'model_b', label: '模型 B（风格化）' },
                          ]}
                        />
                        <div className="flex items-center justify-between">
                          <span className="text-sm">ControlNet（深度/骨骼）</span>
                          <Switch checked={useBoneDepth} onChange={setUseBoneDepth} />
                        </div>
                        <Slider min={3} max={12} defaultValue={5} />
                      </Space>
                    </div>
                  )}
```

---

- [ ] **Step 8.5：在"生成"区块添加"选择模型"Popover 按钮**

找到 gen_ref tab 内的"生成"cs-group（约 4981–4991 行）：

```tsx
                  <div className="cs-group">
                    <div className="cs-group-title">
                      <ThunderboltOutlined /> 生成
                    </div>
                    <Space wrap>
                      <Button type="primary" icon={<VideoCameraOutlined />} loading={videoPromptPreviewSubmitting || videoTaskPolling} onClick={() => void openVideoPromptPreview()}>
                        生成视频
                      </Button>
                      {videoTaskStatus ? <span className="text-xs text-gray-500">任务状态：{videoTaskStatus}</span> : null}
                    </Space>
                  </div>
```

替换为：

```tsx
                  <div className="cs-group">
                    <div className="cs-group-title">
                      <ThunderboltOutlined /> 生成
                    </div>
                    <Space direction="vertical" className="w-full" size="small">
                      {/* 选择模型 */}
                      <Popover
                        open={videoModelPickerOpen}
                        onOpenChange={setVideoModelPickerOpen}
                        trigger="click"
                        placement="leftTop"
                        title={<span className="text-sm font-medium">选择视频模型</span>}
                        content={
                          <div style={{ width: 240 }}>
                            {videoModelsLoading ? (
                              <div className="py-3 text-center text-xs text-gray-400">加载中…</div>
                            ) : videoModels.length === 0 ? (
                              <div className="py-3 text-center text-xs text-gray-400">
                                未配置可用视频模型，请前往「模型管理」添加
                              </div>
                            ) : (
                              <div className="space-y-1">
                                {videoModels.map((m) => (
                                  <div
                                    key={m.id}
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => {
                                      setSelectedVideoModelId(m.id === selectedVideoModelId ? null : m.id)
                                      setVideoModelPickerOpen(false)
                                    }}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter' || e.key === ' ') {
                                        setSelectedVideoModelId(m.id === selectedVideoModelId ? null : m.id)
                                        setVideoModelPickerOpen(false)
                                      }
                                    }}
                                    className={[
                                      'flex cursor-pointer items-start gap-2 rounded-lg px-3 py-2 transition-colors select-none',
                                      selectedVideoModelId === m.id
                                        ? 'bg-blue-50 ring-1 ring-blue-400'
                                        : 'hover:bg-gray-50',
                                    ].join(' ')}
                                  >
                                    <div className="flex-1 min-w-0">
                                      <div className="flex items-center gap-1.5">
                                        <span className="text-sm font-medium text-gray-800 truncate">{m.name}</span>
                                        {m.is_default && (
                                          <Tag color="orange" className="text-[10px] leading-4 px-1 py-0 m-0 flex-shrink-0">默认</Tag>
                                        )}
                                      </div>
                                      <div className="text-xs text-gray-400 mt-0.5">{m.provider_name}</div>
                                    </div>
                                    {selectedVideoModelId === m.id && (
                                      <CheckOutlined className="text-blue-500 mt-0.5 flex-shrink-0" />
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        }
                      >
                        <Button size="small" loading={videoModelsLoading} className="w-full" style={{ textAlign: 'left' }}>
                          <AppstoreOutlined />
                          {selectedVideoModelId
                            ? (videoModels.find((m) => m.id === selectedVideoModelId)?.name ?? '已选模型')
                            : '选择模型（默认）'}
                        </Button>
                      </Popover>
                      {/* 生成 */}
                      <Button
                        type="primary"
                        block
                        icon={<VideoCameraOutlined />}
                        loading={videoPromptPreviewSubmitting || videoTaskPolling}
                        onClick={() => void openVideoPromptPreview()}
                      >
                        生成视频
                      </Button>
                      {videoTaskStatus ? <span className="text-xs text-gray-500">任务状态：{videoTaskStatus}</span> : null}
                    </Space>
                  </div>
```

> **注意**：`Popover` 已在 Ant Design 5 的 import 中（文件顶部 `import { ..., Popover, ... } from 'antd'`）；如尚未引入，需在 antd import 行新增 `Popover`。

---

- [ ] **Step 8.6：视频生成调用传入 `model_id`，硬编码 `text_only`**

找到约第 2820 行 `videoPromptDraft` 的 `submit` 函数内的调用：

```tsx
      const created = await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
        requestBody: {
          shot_id: selectedShot.id,
          reference_mode: context.referenceMode,
          prompt: (derived.prompt || '').trim(),
          images: derived.images,
          ratio,
        } as any,
      })
```

替换为：

```tsx
      const created = await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
        requestBody: {
          shot_id: selectedShot.id,
          reference_mode: 'text_only',
          prompt: (derived.prompt || '').trim(),
          images: [],
          ratio,
          model_id: selectedVideoModelId,
        } as any,
      })
```

找到约第 1212 行 `handleBatchGenerateAll` 的调用：

```tsx
        await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
          requestBody: {
            shot_id: shot.id,
            reference_mode: 'text_only',
            prompt,
            images,
            ratio,
          } as any,
        })
```

替换为：

```tsx
        await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
          requestBody: {
            shot_id: shot.id,
            reference_mode: 'text_only',
            prompt,
            images: [],
            ratio,
            model_id: selectedVideoModelId,
          } as any,
        })
```

---

- [ ] **Step 8.7：检查并补充 Popover import**

检查文件顶部 antd import 行（约第 2 行）是否包含 `Popover`：

```tsx
import {
  Button,
  Card,
  Divider,
  Dropdown,
  Image,
  Input,
  Layout,
  Modal,
  Popover,
  Radio,
  ...
```

若没有 `Popover`，在现有 antd import 中追加它。

---

- [ ] **Step 8.8：typecheck 验证**

```bash
cd front
pnpm run typecheck
```

期望输出：无错误（若有 `noUnusedLocals` 报错，按报错信息定位并删除对应声明）

---

- [ ] **Step 8.9：commit**

```bash
git add front/src/pages/aiStudio/chapter/ChapterStudio.tsx
git commit -m "feat: video gen panel — remove reference selector, add model picker popover (text_only mode)"
```

---

## Task 9：后端完整测试 & 前端 lint

- [ ] **Step 9.1：后端快速验证**

```bash
cd backend
uv run pytest tests/test_llm_picker_api.py tests/test_generated_video_service.py tests/test_llm_api_responses.py -q
```

期望输出：所有测试通过

- [ ] **Step 9.2：前端 lint**

```bash
cd front
pnpm run lint
```

期望输出：无 ESLint 错误（警告可接受）

- [ ] **Step 9.3：前端 typecheck 最终验证**

```bash
cd front
pnpm run typecheck
```

期望输出：无 TypeScript 错误

---

## Task 10：前端 —— 资产编辑页模型选择器

在所有资产编辑页（角色/演员/场景/道具/服装）的"基础信息展示"面板中，在"标签"字段下方插入巨日禄风格的图片模型卡片选择器，所选 model_id 随图片生成请求下发。

**代码定位（基于 `AssetEditPageBase.tsx`）：**
- `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`
  - "标签"字段 JSX：约第 769–772 行（`<div className="text-gray-600 ...">标签...</div>` + Input）
  - `createGenerationTask` prop 类型声明：第 96 行
  - `createGenerationTask` 调用：第 537 行（`createGenerationTask(assetId, image.id, { prompt, images: mentionedFileIds })`）
- `front/src/pages/aiStudio/assets/assetAdapters.ts`
  - 5 处 `createGenerationTask` 实现（character/actor/scene/prop/costume），约第 61、105、149、194、239 行，均已传 `model_id: null`（`as any`）

**后端**：`AssetImageTaskRequest`（`backend/app/api/v1/routes/studio/image_tasks.py:65`）已有 `model_id: str | None` 字段，无需修改。

**注意**：`ModelPickerGrid` 和 `useGenerationModels` 位于 `chapter/` 子目录。从 `assets/components/` 引用时需用跨目录相对路径（`../../chapter/...`）。

**Files:**
- Modify: `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`
- Modify: `front/src/pages/aiStudio/assets/assetAdapters.ts`

---

- [ ] **Step 10.1：更新 `AssetEditPageBase.tsx` —— 导入 hook 和组件**

在文件顶部 import 区域追加（在现有 import 之后）：

```tsx
import { useGenerationModels } from '../../chapter/hooks/useGenerationModels'
import { ModelPickerGrid } from '../../chapter/components/ModelPickerGrid'
```

---

- [ ] **Step 10.2：更新 `createGenerationTask` prop 类型，加入 `model_id`**

找到第 96 行：

```typescript
  createGenerationTask: (assetId: string, imageId: number, payload: { prompt: string; images: string[] }) => Promise<string | null>
```

改为：

```typescript
  createGenerationTask: (assetId: string, imageId: number, payload: { prompt: string; images: string[]; model_id: string | null }) => Promise<string | null>
```

---

- [ ] **Step 10.3：添加 `selectedImageModelId` 状态和 hook 调用**

在组件函数体内，`const [savingBase, setSavingBase] = useState(false)` 之后，追加：

```tsx
  const { models: imageModels, loading: imageModelsLoading } = useGenerationModels('image')
  const [selectedImageModelId, setSelectedImageModelId] = useState<string | null>(null)
```

---

- [ ] **Step 10.4：在"标签"字段后插入 `ModelPickerGrid`**

找到约第 769–772 行的"标签"div：

```tsx
                <div>
                  <div className="text-gray-600 text-sm mb-1">标签（逗号分隔）</div>
                  <Input value={formTags} onChange={(e) => setFormTags(e.target.value)} disabled={smartDetectBusy || savingBase} />
                </div>
```

在其之后（约第 773 行，`</div>` 闭合基础信息 section 之前），插入：

```tsx
                <div>
                  <div className="text-gray-600 text-sm mb-1">选择模型</div>
                  <ModelPickerGrid
                    models={imageModels}
                    loading={imageModelsLoading}
                    selectedId={selectedImageModelId}
                    onChange={setSelectedImageModelId}
                    hint="不选则使用系统默认图片模型"
                  />
                </div>
```

---

- [ ] **Step 10.5：更新 `createGenerationTask` 调用，传入 `model_id`**

找到约第 537 行：

```tsx
      const taskId = await createGenerationTask(assetId, image.id, {
        prompt,
        images: mentionedFileIds,
      })
```

改为：

```tsx
      const taskId = await createGenerationTask(assetId, image.id, {
        prompt,
        images: mentionedFileIds,
        model_id: selectedImageModelId,
      })
```

---

- [ ] **Step 10.6：更新 `assetAdapters.ts`，5 处实现传入 `payload.model_id`**

对 `character`（约第 61–67 行）、`actor`（约第 105 行）、`scene`（约第 149 行）、`prop`（约第 194 行）、`costume`（约第 239 行）的 `createGenerationTask` 实现，将各处签名和请求体同步更新，以 character 为例：

找到：

```typescript
    createGenerationTask: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.createCharacterImageGenerationTaskApiV1StudioImageTasksCharactersCharacterIdImageTasksPost({
        characterId: id,
        requestBody: { image_id: imageId, model_id: null, prompt: payload.prompt, images: payload.images } as any,
      })
      return res.data?.task_id ?? null
    },
```

改为：

```typescript
    createGenerationTask: async (id: string, imageId: number, payload: { prompt: string; images: string[]; model_id: string | null }) => {
      const res = await StudioImageTasksService.createCharacterImageGenerationTaskApiV1StudioImageTasksCharactersCharacterIdImageTasksPost({
        characterId: id,
        requestBody: { image_id: imageId, model_id: payload.model_id, prompt: payload.prompt, images: payload.images } as any,
      })
      return res.data?.task_id ?? null
    },
```

对 actor / scene / prop / costume 的同名字段做相同改法（签名加 `model_id: string | null`，请求体 `model_id: payload.model_id`）。

---

- [ ] **Step 10.7：typecheck 验证**

```bash
cd front
pnpm run typecheck
```

期望输出：无 TypeScript 错误

---

- [ ] **Step 10.8：commit**

```bash
git add front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx front/src/pages/aiStudio/assets/assetAdapters.ts
git commit -m "feat: add image model picker to asset edit page below tags field"
```

---

## Self-Review Checklist

### Spec coverage

| 需求 | 覆盖任务 |
|------|---------|
| 图片生成界面新增模型选择 | Task 7 |
| 视频生成界面新增模型选择 | Task 8 |
| 资产编辑页新增模型选择 | Task 10 |
| 参考巨日禄卡片风格 | Task 6（ModelPickerGrid 卡片宫格） |
| 仅接入百炼系列模型 | 不影响代码；接口自动按 DB 已配置模型返回 |
| 后端接受前端传来的 model_id（视频） | Task 1+2 |
| 后端接受前端传来的 model_id（图片） | 已有，Task 7 传参修正 |
| 资产图片生成传 model_id | Task 10（后端已有字段，适配器已用 as any 传 null，本任务传真实选择） |
| 前端 typecheck 通过 | Task 4, 5, 6, 7, 8, 10 均含验证步骤 |
| openapi:update 同步 | Task 4 |

### 风险点

1. **路由顺序**（Task 3.5）：`/models/picker` 必须在 `/models/{model_id}` 之前定义，否则 FastAPI 将 "picker" 解析为 model_id，返回 404。执行前检查 `llm.py` 中 `GET /models/{model_id}` 的注册位置。

2. **`as any` 绕过类型**（Task 8.3）：视频请求体目前用 `as any` 绕过，`model_id` 字段在 openapi:update 后会正确类型化，届时可移除 `as any`。

3. **`selectedImageModelId` 跨分镜切换不重置**：当前设计中，用户切换分镜时图片模型选择不重置（是预期行为：用户设定一次后批量生成复用同一模型）。若需要分镜级别隔离，可改为 `Record<shotId, modelId>` 存储，本期不做此复杂化。

4. **批量生成函数（`runBatchGenerate`）**：此函数在 Task 7.4 中已更新传 `selectedImageModelId`。该函数在组件闭包中引用状态，天然跟随当前选择，无需额外处理。

5. **跨目录 import（Task 10）**：`AssetEditPageBase.tsx` 从 `chapter/` 引用共享组件，路径为 `../../chapter/hooks/useGenerationModels` 和 `../../chapter/components/ModelPickerGrid`。若将来重构为共享目录，将两个文件移到 `front/src/pages/aiStudio/shared/` 并更新所有 import 即可。
