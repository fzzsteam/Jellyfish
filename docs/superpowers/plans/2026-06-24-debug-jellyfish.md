# debug-jellyfish Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 `.claude/skills/debug-jellyfish.md`——一个给 AI 用的 Jellyfish 问题排查流程 skill，用户贴报错/描述问题时按 4 步流程（探测环境 → 症状分流 → 取证 → 定位根因）排查，只读取证。

**Architecture:** 单 Markdown 文件，用「锚点追加」模式分 5 个任务逐步构建，每段独立 commit。内容套用 `systematic-debugging` 纪律 + 项目特定取证手段（解析 `backend/.env` 的 `DATABASE_URL`、探测 A/B 两种本地启动方式、积分计费/生成任务高频域 playbook）。所有 bash 取证命令均已在本机实测过。

**Tech Stack:** Markdown skill（YAML frontmatter）+ bash 取证（`mysql` / `redis-cli` / `docker ps` / `pgrep`，`celery` 走 `uv run`）。

**关联 spec:** `docs/superpowers/specs/2026-06-24-debug-jellyfish-skill-design.md`

---

## File Structure

- **Create:** `.claude/skills/debug-jellyfish.md`（唯一产物。分 5 任务构建，跟随现有 `.claude/skills/docker-build-push.md` 风格，但补 YAML frontmatter）

**构建模式（锚点追加）：** Task 1 用 Write 创建文件，末尾留占位锚点 `<!-- BUILD ANCHOR -->`；Task 2–4 各用一个 Edit 把锚点替换为「新段落 + 锚点」；Task 5 最后一次 Edit 写入收尾段落并删除锚点。每个任务一次提交，进度可见、可独立回滚。

**已核实的真实事实（写文档时直接引用，勿改动）：**
- 库连接：解析 `backend/.env` 的 `DATABASE_URL`，当前实测 `mysql+aiomysql://jellyfish@localhost:3307/jellyfish`（**端口 3307**）
- 客户端：`mysql`=`/usr/bin/mysql`、`redis-cli`=`/usr/bin/redis-cli`、`celery` 未装（用 `uv run celery`）
- 当前实测为**方式 A**：容器 `compose_mysql_1/redis_1/rustfs_1`（healthy）+ 宿主机 `uvicorn app.main:app`（:8000），**无 celery 进程**
- `docker compose -f ...` 子命令在本机**不可用**（报 unknown flag），探测一律用 `docker ps`
- 积分表：`user_points`、`point_transactions`（含 `cascade_group_id`）；Redis 锁 `points:user:{user_id}`（`app/services/points/locks.py`，超时 `PointsOperationBusyError`）
- 任务表：`generation_tasks`，status `pending/running/streaming/succeeded/failed/cancelled`，`error` 列，索引 `status+updated_at`
- provider 日志关键词：`[BailianVideo]`/`[BailianImage]`、`bailian.images`/`bailian.video`、openai、volcengine、vidu

---

### Task 1: 骨架 —— frontmatter + 标题 + 安全红线

**Files:**
- Create: `.claude/skills/debug-jellyfish.md`

- [ ] **Step 1: 创建文件（frontmatter + 标题 + 红线 + 构建锚点）**

写入 `.claude/skills/debug-jellyfish.md`：

````markdown
---
name: debug-jellyfish
description: 排查 Jellyfish（AI 短剧工作台，FastAPI+Celery+MySQL+Redis）问题时使用。用户贴报错或描述问题（积分对不上、任务卡住、生成失败、连不上、行为异常等）时，按 4 步流程排查：探测环境 → 症状分流 → 取证 → 定位根因。只读取证，绝不臆测；数据库连接走 backend/.env 的 DATABASE_URL，不假设端口。
---

# debug-jellyfish — Jellyfish 问题排查

给 AI 用的项目排查流程。用户报错/报问题时**先取证再下结论**，套用 systematic-debugging 纪律（取证 → 假设 → 验证），禁止在取证前下结论。

## 🔒 安全红线（排查前必读）

- **数据库只读**：仅 `SELECT` / `SHOW` / `DESC` / `EXPLAIN`；禁止 `INSERT` / `UPDATE` / `DELETE` / `DROP` / `ALTER` / `CREATE` 等任何写或 DDL。
- **只查不改**：不修改 `.env` / 配置 / Celery 任务；Redis 只 `GET` / `KEYS`，不 `SET` / `DEL`。
- **凭证不外泄**：DB 密码只用于连接，不写入回复、提交或 skill 正文。

<!-- BUILD ANCHOR -->
````

- [ ] **Step 2: 验证 frontmatter 正确**

Run: `rg -n '^name: debug-jellyfish$' .claude/skills/debug-jellyfish.md`
Expected: 命中 1 行（`2:name: debug-jellyfish`）

Run: `rg -c '^description: 排查 Jellyfish' .claude/skills/debug-jellyfish.md`
Expected: `1`

- [ ] **Step 3: 提交**

```bash
git add .claude/skills/debug-jellyfish.md
git commit -m "feat(debug-jellyfish): skill 骨架——frontmatter + 安全红线"
```

---

### Task 2: Step 0 探测取证环境

**Files:**
- Modify: `.claude/skills/debug-jellyfish.md`（替换 `<!-- BUILD ANCHOR -->`）

- [ ] **Step 1: 写入 Step 0 段落**

Edit：`old_string` = `<!-- BUILD ANCHOR -->`，`new_string` =

````markdown
## Step 0 · 探测取证环境（每次排查最先做）

产出「取证上下文」：库连接（含端口）+ 日志获取方式 + redis/celery 入口。后续所有取证复用此上下文。

### 0.1 解析数据库连接（端口不要假设）

```bash
python3 - <<'PY'
import re
from pathlib import Path
url=next((l.split('=',1)[1].strip() for l in Path('backend/.env').read_text().splitlines() if l.startswith('DATABASE_URL=')),'')
scheme=url.split('://')[0]
print('engine=', 'mysql' if 'mysql' in scheme else ('sqlite' if 'sqlite' in scheme else scheme))
m=re.match(r'^[^:]+://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)$', url)
print('user=%s host=%s port=%s db=%s' % (m.group(1),m.group(3),m.group(4) or '3306',m.group(5))) if m else print('url=', url)
PY
```

实测输出（mysql + 方式 A）：

```
engine= mysql
user=jellyfish host=localhost port=3307 db=jellyfish
```

> 端口是 **3307**，不是默认 3306。后续 mysql 命令一律用这里解析出的 `port`。`engine=sqlite` 时改用 `sqlite3 backend/jellyfish.db`。

### 0.2 探测启动方式（决定日志怎么取）

```bash
docker ps --format '{{.Names}} {{.Status}}' | rg -i 'mysql|redis|rustfs|backend|celery'
pgrep -af 'uvicorn app.main|celery -A|celery worker' | rg -v 'pgrep|/bin/(zsh|bash)'
```

判断规则：

- `docker ps` 命中 `backend` / `celery-worker` → **方式 B（全 docker）**，日志走 `docker logs <容器名>` 或 `docker compose logs`。
- 仅 infra 容器（`mysql` / `redis` / `rustfs`）+ `pgrep` 命中 uvicorn/celery → **方式 A（本地服务）**，日志在宿主机进程 stdout（AI 抓不到 → 需让用户贴报错，或复现时重定向到文件再读）。
- `pgrep` 无 celery → **celery 未启动**，异步任务（生成、积分对账）不执行，常是「任务一直 pending」的根因。

> 本机 `docker compose -f ...` 子命令不可用，统一用 `docker ps` / `docker logs`。

<!-- BUILD ANCHOR -->
````

- [ ] **Step 2: 实测 0.1 解析命令**

Run:
```bash
python3 - <<'PY'
import re
from pathlib import Path
url=next((l.split('=',1)[1].strip() for l in Path('backend/.env').read_text().splitlines() if l.startswith('DATABASE_URL=')),'')
scheme=url.split('://')[0]
print('engine=', 'mysql' if 'mysql' in scheme else ('sqlite' if 'sqlite' in scheme else scheme))
m=re.match(r'^[^:]+://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)$', url)
print('user=%s host=%s port=%s db=%s' % (m.group(1),m.group(3),m.group(4) or '3306',m.group(5))) if m else print('url=', url)
PY
```
Expected: `engine= mysql` 与 `port=3307`（与文档示例一致）

- [ ] **Step 3: 实测 0.2 探测命令，确认方式 A 判定成立**

Run: `docker ps --format '{{.Names}} {{.Status}}' | rg -i 'mysql|redis|rustfs|backend|celery'`
Expected: 命中 `compose_mysql_1` / `compose_redis_1` / `compose_rustfs_1`，**无** backend/celery

Run: `pgrep -af 'uvicorn app.main|celery -A|celery worker' | rg -v 'pgrep|/bin/(zsh|bash)'`
Expected: 命中 `uv run uvicorn app.main:app`，**无** celery

- [ ] **Step 4: 提交**

```bash
git add .claude/skills/debug-jellyfish.md
git commit -m "feat(debug-jellyfish): Step 0 探测取证环境（解析 DATABASE_URL + 启动方式）"
```

---

### Task 3: Step 1 症状分流 + Step 2 取证命令

**Files:**
- Modify: `.claude/skills/debug-jellyfish.md`（替换 `<!-- BUILD ANCHOR -->`）

- [ ] **Step 1: 写入 Step 1 + Step 2 段落**

Edit：`old_string` = `<!-- BUILD ANCHOR -->`，`new_string` =

````markdown
## Step 1 · 症状分流（用户贴错误/描述问题 → 归类 → 决定先取证哪个）

| 症状 | 先取证 |
|---|---|
| 报错 / 异常 / 5xx / 堆栈 | 日志（按 Step 0 方式） |
| 数据对不上（积分 / 状态 / 数量） | 数据库只读查表 |
| 任务卡住 / 一直 pending | `generation_tasks` 表 + Celery 队列 + Redis 锁 |
| 连不上 / 配置 / 环境 | `backend/.env` + compose + `app/config.py` |
| 行为异常无报错 | 读对应 service/chain 源码理解逻辑 |
| 前端异常 | chrome-devtools MCP 看 console/network |

## Step 2 · 取证命令（复用 Step 0 上下文）

- **数据库（只读，端口取自 0.1，密码用 MYSQL_PWD 不进进程列表）**：

```bash
PASS=$(python3 -c "import re,pathlib;u=next(l for l in pathlib.Path('backend/.env').read_text().splitlines() if l.startswith('DATABASE_URL='));print(re.match(r'[^:]+://[^:]+:([^@]+)@',u).group(1))")
MYSQL_PWD="$PASS" mysql -h localhost -P 3307 -u jellyfish jellyfish -e "SELECT ... LIMIT 50;"
```

- **日志**：
  - 方式 B：`docker logs --tail 200 <backend容器名>` 或 celery-worker 容器，`| rg -i '<关键词>'`
  - 方式 A：宿主机进程日志（需用户贴报错，或复现时重定向 `uv run uvicorn ... 2>&1 | tee /tmp/jf-api.log` 后再读）

- **Redis**：`redis-cli -h localhost -p 6379 KEYS 'points:user:*'`、`GET points:user:<uid>`

- **Celery**：
  - 方式 A：`cd backend && uv run celery -A app.core.celery_app:celery_app inspect active`
  - 方式 B：`docker exec <celery-worker容器> celery -A app.core.celery_app:celery_app inspect active`

<!-- BUILD ANCHOR -->
````

- [ ] **Step 2: 实测 mysql 只读连接 + 表存在**

Run:
```bash
PASS=$(python3 -c "import re,pathlib;u=next(l for l in pathlib.Path('backend/.env').read_text().splitlines() if l.startswith('DATABASE_URL='));print(re.match(r'[^:]+://[^:]+:([^@]+)@',u).group(1))")
MYSQL_PWD="$PASS" mysql -h localhost -P 3307 -u jellyfish jellyfish -e "SHOW TABLES LIKE 'generation_tasks';" 2>&1 | head
```
Expected: 返回表头 + `generation_tasks` 一行（表存在）。若报连接错误，回到 Step 0 复核端口/容器健康状态。

- [ ] **Step 3: 提交**

```bash
git add .claude/skills/debug-jellyfish.md
git commit -m "feat(debug-jellyfish): Step 1 症状分流 + Step 2 取证命令"
```

---

### Task 4: Step 3 高频域 playbook（积分计费 + 生成任务）

**Files:**
- Modify: `.claude/skills/debug-jellyfish.md`（替换 `<!-- BUILD ANCHOR -->`）

- [ ] **Step 1: 写入 Step 3 段落**

Edit：`old_string` = `<!-- BUILD ANCHOR -->`，`new_string` =

````markdown
## Step 3 · 高频域 playbook（加速器）

### A. 积分计费

- **表**：`user_points`（账户余额）、`point_transactions`（流水，含 `cascade_group_id` 级联分组）。
- **Redis 锁**：`points:user:{user_id}`（前缀 `points:user:`，见 `app/services/points/locks.py`；抢锁超时抛 `PointsOperationBusyError`）。
- **核心 service**：`app/services/points/billing.py` / `locks.py`；冻结逃逸对账走 Celery beat，配置 `points_reconcile_*`（`app/config.py`）。
- **排查路径**：积分对不上 → 按 `user_id` / `cascade_group_id` 汇总 `point_transactions` → 对 `user_points` 余额 → 查是否有逃逸冻结（`points_reconcile_*` 是否跑过）→ 查 billing 日志。
- **取证 SQL**：

```sql
SELECT user_id, SUM(amount) AS net, COUNT(*) AS n
FROM point_transactions WHERE user_id = '<uid>' GROUP BY user_id;
```

- **⚠️ 已知缺口（复核是否已修）**：供应商 API 对 429/5xx 瞬时错误零重试，百炼 429 是首个暴露点 → 可能导致生成失败但积分冻结未正确结算。

### B. 生成任务 / 供应商调用

- **表**：`generation_tasks`。status：`pending` / `running` / `streaming` / `succeeded` / `failed` / `cancelled`；`error` 列；索引 `status+updated_at`。
- **查卡住 / 失败**：

```sql
SELECT id, status, mode, updated_at, LEFT(error,200) AS err
FROM generation_tasks
WHERE status IN ('pending','running','streaming')
ORDER BY updated_at DESC LIMIT 20;
```

- **日志关键词**：`[BailianVideo]` / `[BailianImage]`（logger `bailian.images` / `bailian.video`）、openai、volcengine、vidu；常见信号 `Task submitted` / `Failed to get task_id` / `Unknown status` / `429`。
- **编排逻辑**：`app/core/task_manager/{stores,strategies,manager}.py`、`app/services/film/*`、`app/core/integrations/*`、`http_logging.py`（供应商请求/响应脱敏日志）。

<!-- BUILD ANCHOR -->
````

- [ ] **Step 2: 核对表名 / 枚举 / Redis key 与源码一致**

Run: `rg '__tablename__ = "(user_points|point_transactions|generation_tasks)"' backend/app/models`
Expected: 3 行命中（points.py ×2、task.py ×1）

Run: `rg -n 'LOCK_KEY_PREFIX = "points:user:"' backend/app/services/points/locks.py`
Expected: 命中 1 行

Run: `rg -n '^\s+(pending|running|streaming|succeeded|failed|cancelled) = ' backend/app/models/task.py`
Expected: 命中 6 行（GenerationTaskStatus 全部枚举）

- [ ] **Step 3: 提交**

```bash
git add .claude/skills/debug-jellyfish.md
git commit -m "feat(debug-jellyfish): Step 3 高频域 playbook（积分计费 + 生成任务）"
```

---

### Task 5: Step 4 根因定位 + 常见问题速查表（收尾，删锚点）

**Files:**
- Modify: `.claude/skills/debug-jellyfish.md`（替换 `<!-- BUILD ANCHOR -->`，本次不再留锚点）

- [ ] **Step 1: 写入 Step 4 + 速查表，删除锚点**

Edit：`old_string` = `<!-- BUILD ANCHOR -->`，`new_string` =

````markdown
## Step 4 · 根因定位 → 结论 + 修复建议

按 `systematic-debugging`：取证 → 形成假设 → 验证（必要时再取证下钻）→ 给出**根因 + 修复建议**，或明确「证据不足，需继续查 X」。禁止在取证前下结论；多假设时优先验证可证伪的那个。

## 常见问题速查

| 现象 | 根因方向 |
|---|---|
| 任务一直 pending / 不推进 | celery 未启动（`pgrep` 无 celery）/ 队列堆积 / provider 卡住或 429 |
| 积分冻结不结算 / 余额对不上 | 429 零重试致生成失败未结算 / 对账 beat 未跑 / `point_transactions` 漏记 |
| 连不上数据库 | 端口非 3306（看 `.env` 的 DATABASE_URL）/ scheme 错 / infra 容器没起 |
| 方式 A 抓不到日志 | 进程在宿主机，需复现重定向 `tee` 或让用户贴报错 |
| `docker compose -f ...` 报错 | 本机无 compose 子命令，改用 `docker ps` / `docker logs` |
| 前端报错但后端正常 | 用 chrome-devtools MCP 查 console / network 请求与响应 |
````

- [ ] **Step 2: 自检——无占位符 / 锚点已删 / 各段落齐备**

Run: `rg -n 'BUILD ANCHOR|TBD|TODO|FIXME|<待' .claude/skills/debug-jellyfish.md`
Expected: **无输出**（占位与锚点全部清除）

Run: `rg -c '^## (🔒 安全红线|Step [0-4]|常见问题)' .claude/skills/debug-jellyfish.md`
Expected: `6`（红线 + Step0–4 + 速查表 = 6 个二级标题；Step1/Step2 共一节计数按实际，以无缺漏为准）

Run: `wc -l .claude/skills/debug-jellyfish.md`
Expected: 行数 > 80（内容完整）

- [ ] **Step 3: 对照 spec §9 验收逐条核对**

人工核对（对照 `docs/superpowers/specs/2026-06-24-debug-jellyfish-skill-design.md` §9）：

- [ ] skill 带 frontmatter，文件存在于 `.claude/skills/debug-jellyfish.md`
- [ ] 「积分对不上」能引导到：Step0 探测（端口正确）→ Step1「数据不对」→ Step3A 查 `point_transactions`/`user_points` + `points:user:*` 锁
- [ ] 取证库端口来自解析 `DATABASE_URL`，非硬编码 3306
- [ ] 顶部红线明确只读、不改、凭证不外泄
- [ ] Step1 分流表含前端（chrome-devtools）兜底

- [ ] **Step 4: 提交**

```bash
git add .claude/skills/debug-jellyfish.md
git commit -m "feat(debug-jellyfish): Step 4 根因定位 + 常见问题速查表，skill 完成"
```

---

## Self-Review

**1. Spec coverage（对照 spec 各节）：**
- §1 目标/非目标 → Task 1 frontmatter description + 红线（只读/不改）覆盖 ✓
- §3 数据源（DATABASE_URL 解析 / 两种启动方式 / Redis·Celery）→ Task 2 Step0 + Task 3 Step2 覆盖 ✓
- §4 四步流程 → Task 2(Step0) / Task 3(Step1+Step2) / Task 4(Step3) / Task 5(Step4) 逐节对应 ✓
- §5 frontmatter 触发 → Task 1 ✓
- §6 安全红线 → Task 1 ✓
- §7 文件结构（单文件 + frontmatter）→ Task 1 ✓
- §8 真实事实清单 → 散布于 Task 2–4 内容 + 顶部「已核实事实」表 ✓
- §9 验收 → Task 5 Step3 逐条核对 ✓

**2. Placeholder scan：** 计划内无 TBD/TODO；skill 文档内的 `<uid>`/`<容器名>`/`<关键词>` 为运行时变量（spec 已说明从上下文填入），非占位缺陷。`SELECT ... LIMIT 50` 的 `...` 是示意由 AI 按场景替换，Step3 playbook 已给真实 SQL 模板。

**3. Type consistency：** 表名（`generation_tasks`/`user_points`/`point_transactions`）、枚举（6 个 status）、Redis key（`points:user:{user_id}`）、端口（3307）在各任务与「已核实事实」表中一致。`LOCK_KEY_PREFIX` 与 `locks.py:35` 源码一致。
