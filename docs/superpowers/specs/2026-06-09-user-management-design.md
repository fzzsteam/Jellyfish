# 用户管理功能设计文档

**日期：** 2026-06-09  
**状态：** 已确认，待实现

---

## 背景

Jellyfish 平台当前无任何用户管理机制，所有 API 均为公开访问，前端直接进入项目列表。本次改造目标是引入多用户账号体系，实现项目和资产的严格用户隔离。

---

## 需求范围

- 多用户协作平台，每人有独立账号
- 仅管理员可创建账号（无开放注册）
- 项目、资产、模型配置、提示词模板、素材文件均按用户严格隔离
- 现有历史数据全部归属到初始管理员账号
- 管理员具备完整管理能力：创建用户、重置密码、禁用/启用、查看任意用户数据

---

## 技术方案：JWT 双令牌

采用 JWT 双令牌方案：

- **access_token**：有效期 15 分钟，前端存内存
- **refresh_token**：有效期 7 天，前端存 `localStorage`
- JWT payload 携带 `{ user_id, token_version }`
- `token_version` 字段：管理员禁用账号或重置密码时递增，旧 token 立即失效

---

## Section 1：数据模型

### 新增 `users` 表

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | 主键 |
| `username` | str unique | 唯一用户名 |
| `hashed_password` | str | bcrypt 哈希密码 |
| `is_admin` | bool = False | 是否管理员 |
| `is_active` | bool = True | 是否启用 |
| `token_version` | int = 0 | token 版本号，递增使所有 token 失效 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

### 需要添加 `user_id` FK 的现有表

| 表 | 说明 |
|---|---|
| `projects` | 项目归属 |
| `actors` | 演员资产 |
| `scenes` | 场景资产 |
| `props` | 道具资产 |
| `costumes` | 服装资产 |
| `prompt_templates` | 提示词模板 |
| `file_items` | 素材文件 |
| `providers` | LLM 供应商配置 |
| `models` | LLM 模型配置 |
| `model_settings` | LLM 模型参数设置 |

`characters`、`shots` 等通过 `project_id → projects.user_id` 间接隔离，无需单独加 `user_id`。

---

## Section 2：认证流程与 API 端点

### 认证流程

```
登录：POST /api/v1/auth/login
  → 验证 username + password
  → 返回 access_token (JWT, 15min) + refresh_token (JWT, 7天)

刷新：POST /api/v1/auth/refresh
  → 携带 refresh_token
  → 验证 token_version 与 DB 一致
  → 返回新 access_token

前端每次请求：Header: Authorization: Bearer <access_token>
```

### 认证端点（公开）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/login` | 登录，返回双 token |
| POST | `/api/v1/auth/refresh` | 刷新 access_token |
| GET | `/api/v1/auth/me` | 获取当前用户信息（需登录） |

### 管理员端点（需 `is_admin=True`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/admin/users` | 创建用户 |
| GET | `/api/v1/admin/users` | 用户列表 |
| GET | `/api/v1/admin/users/{id}` | 用户详情 |
| PATCH | `/api/v1/admin/users/{id}` | 修改用户（重置密码/禁用/启用） |
| GET | `/api/v1/admin/users/{id}/projects` | 以管理员身份查看某用户的项目列表 |

### FastAPI 依赖

```python
# 所有业务路由注入
current_user: User = Depends(get_current_user)

# 管理员路由额外注入
_: User = Depends(require_admin)
```

`get_current_user` 解析 JWT → 查 DB 验证 `token_version` + `is_active`，任一不符返回 401。

---

## Section 3：Service 层改造

### 核心原则

所有查询在 service 层加 `user_id` 过滤，路由层仅负责传入 `current_user.id`，不做任何隔离逻辑。

### 改造模式

```python
# 改造前
async def list_projects(db) -> list[Project]:
    result = await db.execute(select(Project))

# 改造后
async def list_projects(db, user_id: int) -> list[Project]:
    result = await db.execute(
        select(Project).where(Project.user_id == user_id)
    )
```

### 管理员绕过隔离

管理员查看某用户数据时，直接传目标 `user_id`，走同一套 service，不开特权查询路径：

```python
@router.get("/admin/users/{user_id}/projects")
async def admin_list_user_projects(user_id: int, _=Depends(require_admin), db=Depends(get_db)):
    return success_response(await project_service.list_projects(db, user_id))
```

### 涉及改造的 service 文件

| Service | 改造内容 |
|---|---|
| `services/studio/projects.py` | 所有查询加 `user_id` |
| `services/studio/files.py` | 文件列表/上传加 `user_id` |
| `services/studio/assets/` (actors/scenes/props/costumes) | 资产 CRUD 加 `user_id` |
| `services/studio/prompts.py` | 模板查询加 `user_id` |
| `services/llm/` (providers/models/settings) | 模型配置查询加 `user_id` |

---

## Section 4：前端改造

### 认证状态管理

新增 `useAuthStore.ts`（Zustand）：

```ts
interface AuthStore {
  user: { id: number; username: string; is_admin: boolean } | null
  accessToken: string | null
  refreshToken: string | null
  login(username: string, password: string): Promise<void>
  logout(): void
  refresh(): Promise<void>
}
```

`accessToken` 存内存，`refreshToken` 存 `localStorage`。

### OpenAPI 客户端拦截

在请求拦截层统一注入 `Authorization: Bearer <token>`，收到 401 时自动调用 refresh，刷新失败则跳转 `/login`。

### 新增页面

| 路径 | 页面组件 | 说明 |
|---|---|---|
| `/login` | `LoginPage` | 用户名 + 密码登录表单 |
| `/admin/users` | `AdminUserListPage` | 用户列表，支持创建/禁用/启用 |
| `/admin/users/:id` | `AdminUserDetailPage` | 用户详情 + 项目列表 + 重置密码 |

### 路由守卫

```
/login         → 公开
/*             → PrivateRoute（未登录跳 /login）
/admin/*       → AdminRoute（需登录 + is_admin，否则跳首页）
```

### 导航栏

`MainLayout` 右上角新增：用户名/头像 + 退出按钮；管理员账号额外显示"用户管理"入口。

---

## Section 5：数据迁移与初始化

### Alembic Migration 执行顺序

1. 新建 `users` 表
2. 插入初始管理员（从环境变量读取用户名和密码，bcrypt hash 后存入；若变量未设置则迁移报错终止）
3. 对 10 类表逐一添加 `user_id` 可空列，批量 UPDATE 填充为管理员 id，再设为 `NOT NULL` + FK

### 环境变量

| 变量 | 说明 | 是否必填 |
|---|---|---|
| `INITIAL_ADMIN_USERNAME` | 初始管理员用户名，默认 `admin` | 否 |
| `INITIAL_ADMIN_PASSWORD` | 初始管理员密码 | **必填**，未设置则迁移终止 |
| `JWT_SECRET_KEY` | JWT 签名密钥 | **必填** |
| `JWT_ALGORITHM` | 签名算法，默认 `HS256` | 否 |

`.env.example` 中标注必填项并给出示例。

### 新环境初始化

Docker Compose 启动时 Alembic 迁移自动运行，`INITIAL_ADMIN_PASSWORD` 和 `JWT_SECRET_KEY` 在 `.env` 中配置。

---

## 完成检查清单

- [ ] `users` 表 ORM 模型创建
- [ ] 10 类业务表添加 `user_id` FK
- [ ] Alembic migration 编写（含历史数据归属）
- [ ] `app/core/security.py`：JWT 生成/验证、密码 hash
- [ ] `app/api/deps.py`：`get_current_user`、`require_admin` 依赖
- [ ] `app/services/auth.py`：登录、刷新、用户 CRUD
- [ ] `app/api/v1/routes/auth.py`：认证端点
- [ ] `app/api/v1/routes/admin/users.py`：管理员端点
- [ ] 所有 studio/llm service 加 `user_id` 过滤
- [ ] 所有业务路由注入 `current_user`
- [ ] 前端 `useAuthStore.ts`
- [ ] 前端请求拦截器（token 注入 + 自动刷新）
- [ ] 前端 `LoginPage`
- [ ] 前端路由守卫（PrivateRoute / AdminRoute）
- [ ] 前端管理员页面（用户列表 + 详情）
- [ ] 导航栏用户信息 + 退出
- [ ] `.env.example` 更新必填项
- [ ] `pnpm run openapi:update` 同步生成客户端
- [ ] 前端 `pnpm exec tsc --noEmit` 通过
- [ ] 后端相关测试或语法校验通过
