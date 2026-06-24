# debug-jellyfish Skill 设计

> 日期：2026-06-24
> 状态：待实现（spec 已审查通过后转入 writing-plans）
> 作者：brainstorming 协作产出

## 1. 背景与目标

Jellyfish 是 AI 短剧生产工作台（FastAPI + Celery worker/beat + MySQL + Redis + RustFS）。排查问题时，AI 缺少一个统一入口来知道「该查哪、怎么连、命令怎么拼」——每次都要重新摸索连接方式、表名、日志位置。

本 skill 是一个**给 AI 用的项目特定排查流程**：用户贴一个错误或描述一个问题，AI 按固定 4 步路径取证、定位根因，而不是臆测。

**目标**
- 用户报错 / 报问题 → AI 按 4 步流程排查，先取证再下结论。
- 取证命令现成、连接方式项目特定（解析 `backend/.env` 的 `DATABASE_URL`，**绝不假设端口**——当前实际是 `localhost:3307`）。
- 两个高频域（积分计费、生成任务）有加速 playbook，含真实表名 / Redis key / 日志关键词。

**非目标（YAGNI）**
- 不含线上 SAE 排查（SAE 控制台 / 凭证不在本地 skill 范围；如需，仅在 Step1 分流表里留一条「线上」指引占位）。
- 不是给人当手册，是 AI 的「排查大脑」。
- 不替代 `systematic-debugging`，而是在其纪律上叠加本项目取证手段。
- 登录/JWT、数据一致性等不单独开 playbook，只在 Step1 分流表兜底路由。

## 2. 形态决策

采用 **融合方案**：`systematic-debugging` 纪律（取证→假设→验证，不臆测）+ 项目特定取证清单 + 高频域 playbook。

否决的备选：
- 纯「工具/数据源速查册」——没有诊断深度，AI 拿着一堆命令不知道先查哪个。
- 纯「症状路由决策树」——没有项目特异性，缺现成命令和表/key 知识。

## 3. 数据源与连接（项目真实，非公司基建）

> 重要：本项目**不使用**公司 SLS / 数据库堡垒机 / Mars / TAPD MCP，也不用全局 `mysql-readonly-query` skill。所有连接走项目自带配置。

### 3.1 数据库
- 来源：`backend/.env` 的 `DATABASE_URL`（`app/config.py` 的 pydantic Settings 加载）。
- 默认（未配 DATABASE_URL）：sqlite `./jellyfish.db`。
- 本地 MySQL 常见配置（当前实际）：`mysql+aiomysql://jellyfish:***@localhost:3307/jellyfish`（**端口 3307**）。
- 取证：解析 DATABASE_URL 的 scheme/host/port/user/pass/db → 拼 `mysql` cli（scheme 为 sqlite 时改用 `sqlite3`）。
- 表结构参考：`backend/sql/001 ~ 010` 迁移脚本。

### 3.2 两种本地启动方式（决定日志怎么取）
| | 方式 A：infra + 本地服务 | 方式 B：全 docker |
|---|---|---|
| compose 文件 | `deploy/compose/docker-compose.infra.yml`（仅 mysql/redis/rustfs） | `deploy/compose/docker-compose.yml`（全量） |
| backend / celery | 宿主机 `uv run uvicorn` / `uv run celery` | docker 容器（backend / celery-worker / celery-beat） |
| 日志在哪 | 宿主机进程 stdout（AI 抓不到→需复现 / 让用户贴 / 重定向到文件再读） | `docker compose logs backend / celery-worker / celery-beat` |

> 数据库 / Redis 在两种方式下都从宿主机 `localhost:<映射端口>` 访问，一致；差异主要在**日志和 celery 进程怎么找**。

### 3.3 Redis / Celery
- Redis：`backend/.env` 的 `REDIS_HOST/PORT`（默认 `localhost:6379`）。取证用 `redis-cli`。
- Celery：worker + beat（积分冻结对账走 beat tick）。
  - 取证：`uv run celery -A app.core.celery_app:celery_app inspect active`（方式 A）或对 celery-worker 容器 `docker compose exec celery-worker ...`（方式 B）。

## 4. 四步流程

### Step 0 · 探测取证环境（每次排查最先跑，产出「取证上下文」）

1. 读 `backend/.env`，解析 `DATABASE_URL` → 记录 scheme（mysql/sqlite）、host、port、user、db（密码用于连接，不写入任何输出/提交）。
2. 探测启动方式：
   - `docker compose -f deploy/compose/docker-compose.yml ps --services --filter status=running` 是否含 `backend` / `celery-worker` → 命中即**方式 B**。
   - 否则查宿主机 `pgrep -af 'uvicorn|celery'` 有进程 → **方式 A**。
   - 都没有 → 服务未启动，提示用户先启动其中一种，排查中止。
3. 产出本次「取证上下文」：库连接串（已脱敏记录端口/host）、日志获取方式（docker logs / 宿主机）、redis/celery 取证入口。后续所有取证复用此上下文。

### Step 1 · 症状分流（用户贴错误 / 描述问题 → 归类 → 决定先取证哪个）

| 症状 | 先取证 | 兜底 |
|---|---|---|
| 报错 / 异常 / 5xx / 堆栈 | 日志（按 Step0 方式） | 再查关联任务/积分 |
| 数据对不上（积分、状态、数量） | 数据库（只读查表） | 再查日志看写入时刻 |
| 任务卡住 / 不推进 / 一直 pending | `generation_tasks` 表 + Celery 队列 + Redis 锁 | provider 调用日志 |
| 配置 / 环境 / 连不上 | `backend/.env` + compose + `app/config.py` | — |
| 行为与预期不符（无报错） | 读对应 service/chain 源码理解逻辑 | — |

### Step 2 · 取证（现成命令，AI 直接跑，复用 Step0 上下文）

- **数据库（只读）**：
  ```bash
  DB_URL=$(rg '^DATABASE_URL=' backend/.env | cut -d= -f2-)
  # 解析后执行（端口取自解析值，不硬编码）
  mysql -h <host> -P <port> -u <user> -p<pass> <db> -e "SELECT ... LIMIT 50;"
  ```
- **日志**：
  - 方式 B：`docker compose -f deploy/compose/docker-compose.yml logs --tail=200 backend celery-worker | rg -i '<关键词>'`
  - 方式 A：宿主机进程日志（需复现或重定向）；若拿不到，明确告知用户「需要你贴报错/重定向日志」。
- **Redis**：`redis-cli -h <host> -p <port> KEYS 'points:user:*'`、`GET points:user:<uid>`
- **Celery**：`celery -A app.core.celery_app:celery_app inspect active`（或容器内 exec）

### Step 3 · 高频域 playbook（加速器）

#### A. 积分计费
- **表**：`user_points`（账户余额）、`point_transactions`（流水，含 `cascade_group_id` 级联分组）。
- **Redis 锁**：`points:user:{user_id}`（前缀 `points:user:`，见 `app/services/points/locks.py`；抢锁超时抛 `PointsOperationBusyError`）。
- **核心 service**：`app/services/points/billing.py`、`app/services/points/locks.py`；对账（冻结逃逸补偿）走 Celery beat，配置在 `config.py` 的 `points_reconcile_*`。
- **典型排查**：用户积分对不上 → 查 `point_transactions` 按 user_id/cascade_group_id 汇总 → 与 `user_points` 余额对账 → 查是否有逃逸冻结（`points_reconcile_*` 是否跑过）→ 查 billing 日志。
- **⚠️ 已知缺口（实现时复核是否已修）**：供应商 API 对 429/5xx 瞬时错误零重试，百炼 429 是首个暴露点——可能导致生成失败但积分冻结未正确结算（见项目记忆 `provider-api-zero-retry`）。

#### B. 生成任务 / 供应商调用
- **表**：`generation_tasks`。关键字段：`status`（`pending` / `running` / `streaming` / `succeeded` / `failed` / `cancelled`）、`error`、`updated_at`；索引 `ix_generation_tasks_status_updated_at`（适合查卡住任务）。
- **典型排查（卡住/失败）**：
  ```sql
  SELECT id, status, mode, updated_at, LEFT(error,200) AS err
  FROM generation_tasks
  WHERE status IN ('pending','running','streaming')
  ORDER BY updated_at DESC LIMIT 20;
  ```
- **日志关键词**：`[BailianVideo]` / `[BailianImage]`（logger `bailian.images` / `bailian.video`）、openai、volcengine、vidu；常见信号 `Task submitted`、`Failed to get task_id`、`Unknown status`、`429`、`error`。
- **状态机/编排逻辑**：`app/core/task_manager/{stores,strategies,manager}.py`、`app/services/film/*`、`app/core/integrations/*`、`http_logging.py`（供应商请求/响应脱敏日志）。

### Step 4 · 根因定位 → 结论 + 修复建议

按 `systematic-debugging`：取证 → 形成假设 → 验证（必要时再取证下钻）→ 给**根因 + 修复建议**（或明确「证据不足，需继续查 X」）。禁止在取证前下结论。

## 5. frontmatter / 触发设计

```yaml
---
name: debug-jellyfish
description: 排查 Jellyfish（AI 短剧工作台，FastAPI+Celery+MySQL+Redis）问题时使用。用户贴报错/描述问题（积分对不上、任务卡住、生成失败、连不上、行为异常等）时，按 4 步流程（探测环境→症状分流→取证→定位根因）排查；只读取证，绝不臆测。
---
```

- 触发词覆盖：排查 / 报错 / 为什么 / 对不上 / 卡住 / 失败 / pending / 积分 / 生成任务 + Jellyfish 项目上下文。
- 与现有 `.claude/skills/docker-build-push.md`（无 frontmatter）不同，本 skill **必须带 frontmatter**，以便用户报问题时自动激活。

## 6. 安全红线（写进 skill 顶部）

- 数据库**只读**：仅 `SELECT` / `SHOW` / `DESC` / `EXPLAIN`；禁止 `INSERT/UPDATE/DELETE/DROP/ALTER/CREATE` 等。
- **只查不改**：不修改 `.env` / 配置 / Celery 任务 / Redis 数据（只 `GET`/`KEYS`，不 `SET`/`DEL`）。
- 凭证（DB 密码等）只用于连接，**不出现在输出、skill 正文、提交内容里**。

## 7. 文件结构

- 单文件：`.claude/skills/debug-jellyfish.md`（跟随 `docker-build-push.md` 的「固定配置 + 步骤 + 常见问题表」风格，但补 YAML frontmatter）。
- 正文组织：红线 → Step0 探测 → Step1 分流表 → Step2 取证命令 → Step3 高频域 playbook → Step4 定位收尾 → 常见问题速查表（已知坑：端口非 3306、方式A日志抓不到、429 零重试）。

## 8. 实现时需引用的真实事实清单（已核实）

| 项 | 真实值 | 位置 |
|---|---|---|
| 库连接 | 解析 `backend/.env` 的 `DATABASE_URL`（当前 mysql `localhost:3307`） | `app/config.py` |
| 积分账户表 | `user_points` | `app/models/points.py:49` |
| 积分流水表 | `point_transactions`（含 `cascade_group_id`） | `app/models/points.py:75` |
| 积分 Redis 锁 | `points:user:{user_id}`（前缀 `points:user:`，超时 `PointsOperationBusyError`） | `app/services/points/locks.py:35` |
| 积分 service | `billing.py` / `locks.py`；对账配置 `points_reconcile_*` | `app/services/points/`、`config.py:54` |
| 任务表 | `generation_tasks`（status: pending/running/streaming/succeeded/failed/cancelled；error 列；索引 status+updated_at） | `app/models/task.py:22,37` |
| 供应商日志关键词 | `[BailianVideo]`/`[BailianImage]`、`bailian.images`/`bailian.video`、openai、volcengine、vidu | `app/core/integrations/*` |
| 任务编排 | `task_manager/{stores,strategies,manager}.py`、`services/film/*` | `app/core/task_manager/` |
| infra compose | `deploy/compose/docker-compose.infra.yml`（mysql/redis/rustfs） | `deploy/compose/` |
| 全量 compose | `deploy/compose/docker-compose.yml`（含 backend/celery-worker/celery-beat） | `deploy/compose/` |

## 9. 验收标准

- [ ] skill 带 frontmatter，`.claude/skills/debug-jellyfish.md` 存在。
- [ ] 用户报「积分对不上」时，skill 能引导 AI：Step0 探测（端口正确）→ Step1 归到「数据不对」→ Step3A 查 `point_transactions`/`user_points` 对账 + 查 `points:user:*` 锁。
- [ ] 取证命令的库端口来自解析 `DATABASE_URL`，非硬编码 3306。
- [ ] 顶部安全红线明确只读、不改、凭证不外泄。
- [ ] Step1 分流表含「线上 SAE」兜底指引（仅思路，不带凭证）。
