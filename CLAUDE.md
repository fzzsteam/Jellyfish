# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作提供指引。

## 项目概览

Jellyfish 是 AI 驱动的短剧生产工作台，覆盖完整制作流程：剧本输入 → 分镜拆解 → 资产一致性管理 → 图片/视频生成 → 任务追踪。

## 架构

仓库包含三个主要部分：

- **`backend/`** — FastAPI + LangChain/LangGraph + SQLAlchemy 异步 API（Python，uv 管理）
- **`front/`** — React + Vite + Ant Design + Tailwind SPA（TypeScript，pnpm 管理）
- **`site/`** — Hugo 文档站（Go）

### 后端分层结构

```
app/api/v1/routes/    # 收参、鉴权、调 service、返回 ApiResponse
app/services/studio/  # 项目/章节/分镜/文件/图片任务等主业务逻辑
app/services/llm/     # Provider / Model / Settings 管理逻辑
app/services/film/    # 视频生成与分镜帧提示词任务编排
app/core/contracts/   # 生成能力相关的跨层 DTO
app/core/integrations/ # 供应商集成（OpenAI、阿里百炼、火山引擎）
app/core/task_manager/ # 异步任务分派与执行编排
app/chains/           # LangChain PromptTemplate 与 LangGraph 工作流
app/models/           # SQLAlchemy ORM 模型
app/schemas/          # Pydantic 请求/响应 Schema
```

路由层必须保持瘦身（收参 + Depends + 调 service + 返回 ApiResponse），业务逻辑、跨实体校验、存储交互统一下沉到 service。

### 前端 OpenAPI 客户端

所有后端调用统一走生成客户端，不新增手写 service 封装。

生成输出目录：`front/src/services/generated/`  
缓存 Spec：`front/openapi.json`

后端 API 有任何变更后必须重新生成：
```bash
cd front
pnpm run openapi:update   # 需要后端在 http://127.0.0.1:8000 运行
```

### 响应约定

所有接口使用 `ApiResponse` 响应壳，统一使用以下帮助函数：
- `success_response(...)`、`created_response(...)`、`empty_response()`、`paginated_response(...)`
- `entity_not_found(...)`、`entity_already_exists(...)`、`required_field(...)`、`invalid_choice(...)`、`not_belong_to(...)`

### 分镜状态语义

- `shot.status` = 仅表示信息提取确认状态（`pending` | `ready`）
- `video-readiness` = 单独表示是否具备视频生成条件，与 `shot.status` 分离
- 运行时生成状态来自任务系统，不反映在 `shot.status` 上

### 页面职责边界

- **分镜编辑页** = 准备（资产/对白提取、候选确认、基础信息修正、推进到 `ready`）
- **分镜工作室** = 生成（关键帧、参考图、视频参数、发起视频生成）
- **任务中心** = 通用任务状态面板（不承载业务专属上下文详情）

## 常用命令

### 后端

```bash
cd backend
uv sync                          # 安装/同步依赖
uv sync --group dev              # 包含开发依赖（pytest、pylint）
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000  # 开发服务器
uv run pytest -q                 # 运行全量测试
uv run pytest tests/test_common_services.py tests/test_studio_api_responses.py -q  # 快速验证
uv run pylint app                # 代码检查
python -m py_compile $(rg --files app tests)  # 仅做语法检查
```

运行单个测试文件：
```bash
cd backend
uv run pytest tests/<test_file>.py -q
```

运行集成测试（需配置 OPENAI_API_KEY）：
```bash
cd backend
uv run pytest -m integration -q
```

### 前端

```bash
cd front
pnpm install          # 安装依赖
pnpm dev              # 开发服务器
pnpm run typecheck    # tsc --noEmit（前端改动后必须通过）
pnpm run lint         # ESLint
pnpm run build        # 生产构建
```

### Docker Compose（全栈）

```bash
cp deploy/compose/.env.example deploy/compose/.env
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml up --build
```

端口：前端 `7788`、后端 `8000`、MySQL `3306`、Redis `6379`、RustFS `9000`。

## 代码规范（来自 AGENTS.md）

1. API 有变更后必须运行 `pnpm run openapi:update` 同步生成客户端。
2. 前端统一走 OpenAPI 生成客户端，不新增手写 service 封装。
3. 后端严格区分 `api`（收参/鉴权/响应）与 `service`（业务逻辑/状态/编排）。
4. 新增或改动的函数、类必须添加注释，说明"做什么"与"为什么存在"，注释须与实现保持同步。
5. `site/content/docs/` 目录职责：
   - `architecture/` = 当前真实生效的实现
   - `plans/` = 进行中或待推进的改造方案
   - `guide/` = 操作说明 / 开发流程
   - `reference/` = 稳定参考资料
6. `site/content/blog/` = release note，已固化版本未经明确指定不得修改。
7. 生成能力相关通用契约（输入/输出 DTO、供应商配置）统一放 `app/core/contracts/`；`tasks/` 仅负责任务封装与分派；`integrations/` 只依赖 `contracts/`，不依赖 `tasks/` 类型。

## 完成检查清单

满足以下全部条件才算"完成"：
- [ ] 代码实现完成，新增/改动的函数和类已补充必要注释
- [ ] 若后端 API 有变化：已运行 `pnpm run openapi:update`，前端生成类型已同步，前端调用已切到生成客户端
- [ ] 若影响当前系统行为：已更新 `site/content/docs/architecture/`
- [ ] 若影响后续执行计划：已更新 `site/content/docs/plans/`
- [ ] 前端改动通过 `pnpm exec tsc --noEmit`
- [ ] 后端改动通过相关测试或最低限度的语法/导入校验
