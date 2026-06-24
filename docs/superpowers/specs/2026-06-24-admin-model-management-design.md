# 管理员统一模型管理设计文档

**日期**：2026-06-24  
**状态**：已批准，待实现

## 背景

当前架构中，每个用户独立配置自己的模型供应商（Provider）和模型（Model），通过 `user_id` 隔离。需求变更为：只有管理员可以创建和管理全局模型及积分单价，普通用户通过积分调用管理员配好的模型，并可在设置中选择自己的默认模型。

## 目标

1. `Provider` / `Model` 变为全局共享资源，管理员统一维护
2. 写操作（创建/修改/删除 Provider 和 Model）仅限管理员
3. 读操作（列表/详情）对所有登录用户开放
4. `ModelSettings`（默认模型选择）保留每用户一行，用户从全局模型池中选择
5. 前端普通用户只看到"设置"Tab，供应商和模型 Tab 仅管理员可见

## 数据库迁移

**迁移文件**（按顺序执行）：

### 1. 清理非管理员数据

```sql
-- 清理非管理员用户的 model_settings
DELETE FROM model_settings
WHERE user_id NOT IN (SELECT id FROM users WHERE is_admin = TRUE);

-- 清理非管理员用户的 models
DELETE FROM models
WHERE user_id NOT IN (SELECT id FROM users WHERE is_admin = TRUE);

-- 清理非管理员用户的 providers
DELETE FROM providers
WHERE user_id NOT IN (SELECT id FROM users WHERE is_admin = TRUE);
```

### 2. 清理悬空的 model_settings 外键引用

```sql
-- 管理员 model_settings 中指向已删模型的外键置 NULL
UPDATE model_settings
SET default_text_model_id = NULL
WHERE default_text_model_id NOT IN (SELECT id FROM models);

UPDATE model_settings
SET default_image_model_id = NULL
WHERE default_image_model_id NOT IN (SELECT id FROM models);

UPDATE model_settings
SET default_video_model_id = NULL
WHERE default_video_model_id NOT IN (SELECT id FROM models);
```

### 3. 删除 user_id 列

```sql
ALTER TABLE providers DROP COLUMN user_id;
ALTER TABLE models DROP COLUMN user_id;
```

## 后端改造

### 模型层（`app/models/llm.py`）

- `Provider` 和 `Model` 去掉 `UserOwnedMixin` 继承
- `user_id` 列随迁移删除，不再声明
- `created_by` 字段保留做审计

### Service 层（`app/services/llm/manage.py`）

| 函数 | 改动 |
|------|------|
| `list_providers_paginated` | 去掉 `user_id` 参数和 `WHERE user_id=` 过滤 |
| `list_models_paginated` | 同上 |
| `create_provider` | 去掉 `user_id=user_id` 写入；`created_by` 由调用方传入 admin 用户名 |
| `create_model` | 同上；`_require_owned_provider` 改为只校验 provider 存在 |
| `_get_owned_provider` | 改为纯存在性检查，去掉 `user_id` 归属校验 |
| `_get_owned_model` | 同上 |
| `_require_owned_provider` | 只校验 provider 存在且 category 支持，去掉归属校验 |
| `delete_provider` | 去掉 `user_id` 判断，直接删除 |
| `delete_model` | 同上 |
| `get_image_generation_options` | 去掉 `user_id` 参数（或改从全局默认读） |
| `get_video_generation_options` | 同上 |

### 路由层（`app/api/v1/routes/llm.py`）

| 操作 | 依赖改动 |
|------|---------|
| `POST /providers` | `get_current_user` → `require_admin` |
| `PATCH /providers/{id}` | `get_current_user` → `require_admin` |
| `DELETE /providers/{id}` | `get_current_user` → `require_admin` |
| `POST /models` | `get_current_user` → `require_admin` |
| `PATCH /models/{id}` | `get_current_user` → `require_admin` |
| `DELETE /models/{id}` | `get_current_user` → `require_admin` |
| `GET /providers` | 保持 `get_current_user`，去掉 user_id 过滤 |
| `GET /models` | 保持 `get_current_user`，去掉 user_id 过滤 |
| `GET /image-generation-options` | 保持不变 |
| `GET /video-generation-options` | 保持不变 |
| `GET/PUT /model-settings` | 保持不变 |

### resolver.py（`app/services/llm/resolver.py`）

`get_model_by_category` 中通过 `user_id` 查 `ModelSettings` 的逻辑不变。`_resolve_model` 去掉 `user_id` 归属校验（模型已全局），直接按 `model_id` 查。

### openapi 客户端同步

后端改动完成后执行：
```bash
cd front
pnpm run openapi:update
```

## 前端改造

### `ModelManagement.tsx`

从用户信息接口读取 `is_admin` 字段，动态控制 Tabs：

```tsx
// 管理员：供应商 + 模型 + 设置
// 普通用户：仅设置
const tabs = isAdmin
  ? [
      { key: 'providers', label: '供应商' },
      { key: 'models', label: '模型' },
      { key: 'settings', label: '设置' },
    ]
  : [{ key: 'settings', label: '设置' }]
```

普通用户进入模型管理页时，默认激活 `settings` Tab。

### `SettingsTab.tsx`

模型选择下拉框的数据源不变（仍调用 `GET /models`），但接口返回全局模型列表（无 user_id 过滤），普通用户可从中选择默认模型。

### `ProvidersTab.tsx` / `ModelsTab.tsx`

无需改动（普通用户不可见，管理员使用不受影响）。

## 完成检查

- [ ] 迁移 SQL 文件已创建并验证
- [ ] `Provider` / `Model` ORM 模型去掉 `UserOwnedMixin`
- [ ] 写操作路由改为 `require_admin`
- [ ] 读操作去掉 `user_id` 过滤
- [ ] `pnpm run openapi:update` 已执行
- [ ] 前端 `ModelManagement.tsx` 按 `is_admin` 控制 Tab 显示
- [ ] `pnpm exec tsc --noEmit` 通过
