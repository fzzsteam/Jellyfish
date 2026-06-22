# Jellyfish

Jellyfish 是面向 AI 短剧生产的工作台。本文件覆盖两类部署：

- **本地开发**：混合模式（MySQL/Redis/RustFS 跑 Docker，Backend/Celery/Frontend 跑宿主机），便于热更新与查看日志，见下文第 1–7 节。
- **线上部署（SAE）**：单容器镜像（前端产物 + 后端 + Celery 由 supervisord 托管），见文末「线上部署（SAE）」一节。

两类环境都需要执行 `backend/sql/` 下的数据库迁移，区别仅在执行方式：本地用 mysql 客户端、线上用仓库自带的 `backend/apply_migrations.py`（线上容器未安装 mysql 客户端）。

## 服务与端口

| 服务 | 启动方式 | 默认地址 |
| --- | --- | --- |
| Frontend | Vite | <http://localhost:7788> |
| Backend | Uvicorn | <http://localhost:8000> |
| API 文档 | FastAPI | <http://localhost:8000/docs> |
| MySQL | Docker Compose | `127.0.0.1:3307` |
| Redis | Docker Compose | `127.0.0.1:6379` |
| RustFS API | Docker Compose | <http://localhost:9000> |
| RustFS Console | Docker Compose | <http://localhost:9001> |

MySQL、Redis 和 RustFS 的实际端口以 `deploy/compose/.env.local` 为准。修改 Compose 端口后，必须同步修改 `backend/.env`。

## 环境要求

- Docker 和 Docker Compose v2
- Python 3.11 或更高版本
- [uv](https://docs.astral.sh/uv/)
- Node.js 18 或更高版本
- pnpm 9

以下命令默认在仓库根目录执行。

## 1. 准备环境变量

复制本地环境配置：

```bash
cp deploy/compose/.env.local.example deploy/compose/.env.local
cp backend/.env.example backend/.env
```

检查 `deploy/compose/.env.local` 中的基础设施配置，至少包括：

```dotenv
MYSQL_DATABASE=jellyfish
MYSQL_USER=jellyfish
MYSQL_PASSWORD=<local-mysql-password>
MYSQL_PORT=3307

REDIS_PORT=6379
REDIS_DB=0

RUSTFS_ACCESS_KEY=<local-rustfs-access-key>
RUSTFS_SECRET_KEY=<local-rustfs-secret-key>
S3_BUCKET_NAME=jellyfish-assets
RUSTFS_PORT=9000
RUSTFS_CONSOLE_PORT=9001
```

编辑 `backend/.env`，确保它连接到上述宿主机端口：

```dotenv
DATABASE_URL=mysql+aiomysql://jellyfish:<local-mysql-password>@127.0.0.1:3307/jellyfish

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=<local-admin-password>
JWT_SECRET_KEY=<local-random-secret>

CORS_ORIGINS=http://localhost:7788,http://127.0.0.1:7788

S3_ENDPOINT_URL=http://127.0.0.1:9000
S3_ACCESS_KEY_ID=<local-rustfs-access-key>
S3_SECRET_ACCESS_KEY=<local-rustfs-secret-key>
S3_BUCKET_NAME=jellyfish-assets
S3_REGION_NAME=us-east-1
S3_ADDRESSING_STYLE=path
```

不要把真实密码、JWT Secret 或供应商 API Key 提交到 Git。

## 2. 启动基础设施

```bash
docker compose \
  --env-file deploy/compose/.env.local \
  -f deploy/compose/docker-compose.infra.yml \
  up -d
```

检查容器状态：

```bash
docker compose \
  --env-file deploy/compose/.env.local \
  -f deploy/compose/docker-compose.infra.yml \
  ps
```

`mysql` 和 `redis` 应显示为 `healthy`，`rustfs` 应为运行状态，`rustfs-init-bucket` 正常情况下会以退出码 `0` 完成。

查看基础设施日志：

```bash
docker compose \
  --env-file deploy/compose/.env.local \
  -f deploy/compose/docker-compose.infra.yml \
  logs -f mysql redis rustfs
```

## 3. 安装 Backend 依赖并首次启动

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

首次启动会创建当前模型中缺失的表，并使用 `INITIAL_ADMIN_USERNAME` 和 `INITIAL_ADMIN_PASSWORD` 创建初始管理员。看到以下日志后说明 Backend 已启动：

```text
Application startup complete.
```

验证 Backend：

```bash
curl http://127.0.0.1:8000/health
```

预期返回状态码 `200`。API 文档位于 <http://localhost:8000/docs>。

> SQLAlchemy `create_all()` 只会创建缺失表，不会给已有表增加字段。使用过旧版本数据库或复用 Docker Volume 时，仍然必须执行下一节的 SQL 迁移。

## 4. 执行数据库迁移

迁移脚本位于 `backend/sql/`。全新环境和从旧版本升级的环境都应按文件名顺序执行当前脚本；执行 `009` 前必须确保 Backend 已至少成功启动一次，以便创建并播种初始管理员。`010-add-points-billing.sql`（用户积分计费）幂等，可在 `009` 之后的任意时机执行：新增 `user_points` / `point_transactions` 表，给 `models` 加 `unit_points` 列、给 `generation_tasks` 加 `billing_id` 列，并为存量用户回填 `balance=0, frozen=0`、存量模型回填 `unit_points=0`（即默认免费，由管理员按需调价）。

建议先备份重要的本地数据，然后在仓库根目录执行：

```bash
for migration in backend/sql/*.sql; do
  echo "Applying ${migration}"
  docker compose \
    --env-file deploy/compose/.env.local \
    -f deploy/compose/docker-compose.infra.yml \
    exec -T mysql \
    sh -c 'mysql --default-character-set=utf8mb4 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
    < "${migration}" || exit 1
done
```

迁移完成后重启 Backend。

如果只需要修复以下错误：

```text
Unknown column 'generation_tasks.user_id' in 'where clause'
```

可以单独执行用户隔离迁移：

```bash
docker compose \
  --env-file deploy/compose/.env.local \
  -f deploy/compose/docker-compose.infra.yml \
  exec -T mysql \
  sh -c 'mysql --default-character-set=utf8mb4 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
  < backend/sql/009-add-users-and-user-isolation.sql
```

这些命令不是交互式进入 MySQL，而是把宿主机上的 SQL 文件传给容器内的 MySQL 客户端执行。

## 5. 启动 Backend

终端 1：

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 6. 启动 Celery Worker

Worker 与 Backend 共用 `backend/.env`。启动前确认 Redis 容器为 `healthy`，且 `REDIS_PORT` 与 Compose 配置一致。

终端 2：

```bash
cd backend
uv run celery \
  -A app.core.celery_app:celery_app \
  worker \
  -l info
```

看到类似以下日志说明 Worker 已连接 Broker 并准备接收任务：

```text
celery@<hostname> ready.
```

## 6.1. 启动 Celery Beat（定时任务调度）

Beat 负责周期性任务调度，当前已注册 `points.reconcile_stale_freezes`（积分冻结对账，每 300 秒一次）。开发环境可在终端 2-b 启动：

```bash
cd backend
uv run celery \
  -A app.core.celery_app:celery_app \
  beat \
  -l info
```

看到类似以下日志说明 Beat 已启动：

```text
celery beat v5.x.x is starting.
Scheduler: Sending due task reconcile-stale-point-freezes
```

> **生产环境必须只运行一个 Beat 进程**：Docker Compose 部署用 `celery-beat` 服务（见 `deploy/compose/docker-compose.yml`），SAE 单容器部署用 supervisord 的 `[program:beat]`（见 `deploy/docker/supervisord.conf`），**两者只能选其一**，切勿同时启用，否则同一个定时任务会被重复触发。两份配置已互相注释说明，切换部署形态时同步调整。

## 7. 启动 Frontend

终端 3：

```bash
cd front
pnpm install
pnpm dev
```

Vite 会打开 <http://localhost:7788>。Frontend 默认请求 <http://localhost:8000>。

## 推荐启动顺序

1. 启动 Docker Desktop。
2. 启动 MySQL、Redis 和 RustFS。
3. 配置并首次启动 Backend，确保管理员已创建。
4. 执行数据库迁移并重启 Backend。
5. 启动 Celery Worker。
6. 启动 Frontend。

日常开发时，如果数据库已经迁移到当前版本，只需执行第 2、5、6、7 节中的启动命令。

## 验证清单

```bash
# Backend 健康检查
curl -f http://127.0.0.1:8000/health

# MySQL
docker compose \
  --env-file deploy/compose/.env.local \
  -f deploy/compose/docker-compose.infra.yml \
  exec mysql \
  sh -c 'mysqladmin ping -h 127.0.0.1 -u root -p"$MYSQL_ROOT_PASSWORD"'

# Redis
docker compose \
  --env-file deploy/compose/.env.local \
  -f deploy/compose/docker-compose.infra.yml \
  exec redis redis-cli ping
```

同时确认：

- Backend 日志没有数据库或 Redis 连接异常。
- Worker 日志包含 `ready`。
- <http://localhost:7788> 可以打开并完成登录。
- <http://localhost:8000/docs> 可以打开。

## 停止服务

Backend、Worker 和 Frontend 分别在对应终端按 `Ctrl+C` 停止。

停止基础设施但保留数据：

```bash
docker compose \
  --env-file deploy/compose/.env.local \
  -f deploy/compose/docker-compose.infra.yml \
  down
```

删除基础设施及所有本地 MySQL/RustFS 数据：

```bash
# 危险：此命令会永久删除 Compose Volume 中的本地数据
docker compose \
  --env-file deploy/compose/.env.local \
  -f deploy/compose/docker-compose.infra.yml \
  down -v
```

## 常见问题

### Backend 无法连接 MySQL

典型错误：

```text
Can't connect to MySQL server on '127.0.0.1'
```

依次检查：

1. `docker compose ... ps` 中 MySQL 是否为 `healthy`。
2. `deploy/compose/.env.local` 的 `MYSQL_PORT` 是否与 `backend/.env` 的 `DATABASE_URL` 一致。
3. MySQL 容器是否因为 Docker Desktop 重启而处于 `exited` 状态。

### Backend 拒绝启动并提示缺少初始管理员密码

典型错误：

```text
INITIAL_ADMIN_PASSWORD is not set; refusing to start without an initial admin account
```

在 `backend/.env` 中设置非空的 `INITIAL_ADMIN_PASSWORD`，然后重新启动 Backend。

### 浏览器显示 CORS 错误

先确认 `backend/.env` 包含：

```dotenv
CORS_ORIGINS=http://localhost:7788,http://127.0.0.1:7788
```

如果健康检查的响应包含 CORS Header，但某个业务接口仍显示 CORS 错误，应优先查看 Backend 终端。未处理的 HTTP 500 响应可能没有附带 CORS Header，浏览器会把真实后端异常表现为 CORS 错误。

### 接口提示数据库字段不存在

典型错误：

```text
Unknown column 'generation_tasks.user_id'
```

这是存量数据库未执行迁移，不是 CORS 问题。按“执行数据库迁移”一节运行对应 SQL。

### Worker 无法连接 Redis

确认：

- Redis 容器为 `healthy`。
- `backend/.env` 中的 `REDIS_HOST` 为 `127.0.0.1`。
- `backend/.env` 中的 `REDIS_PORT` 与 `deploy/compose/.env.local` 一致。
- 如果设置了 `CELERY_BROKER_URL`，其中的地址没有覆盖成错误端口。

## 线上部署（SAE）

线上采用单容器部署：`deploy/docker/combined.Dockerfile` 构建一个镜像，包含前端静态产物 + 后端 + Celery，由 supervisord 统一托管（`web` = uvicorn，`worker` = celery）。适用于阿里云 SAE 等按容器镜像部署的 Serverless 平台。

> 与本地不同：线上容器**未安装 mysql 命令行客户端**，数据库迁移只能用仓库自带的 Python 脚本 `backend/apply_migrations.py` 执行。

### 1. 构建并推送镜像

```bash
docker build -f deploy/docker/combined.Dockerfile -t <registry>/jellyfish:<tag> .
docker push <registry>/jellyfish:<tag>
```

`backend/apply_migrations.py` 与 `backend/sql/` 会随 `COPY backend/ ./` 一并打进镜像，部署前务必确认它们已提交到仓库。

### 2. SAE 环境变量

在 SAE 应用配置中注入以下环境变量（应用与迁移脚本共用同一份 `DATABASE_URL`）：

| 变量 | 必要性 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 必设 | 线上 MySQL，如 `mysql+aiomysql://user:pass@host:3306/jellyfish` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | 必设 | Celery broker |
| `S3_ENDPOINT_URL` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` / `S3_BUCKET_NAME` | 必设 | 对象存储 |
| `INITIAL_ADMIN_USERNAME` | 可选 | 默认 `admin` |
| `INITIAL_ADMIN_PASSWORD` | 首次或无管理员时必设 | `users` 表无管理员时用它播种首个账号；不设且表空 → 应用拒绝启动 |
| `JWT_SECRET_KEY` | 强烈建议改 | 默认为弱值，务必改为随机字符串 |
| `CORS_ORIGINS` | 按需 | 前端域名（逗号分隔）；同源部署可不设 |
| `OPENAI_API_KEY` 等 | 按需 | 真实调用大模型才需要 |

### 3. 数据库迁移

部署后通过 SAE Webshell（或「执行命令」）进入容器，按文件名顺序幂等执行 `backend/sql/*.sql`：

```bash
cd /app
uv run python apply_migrations.py          # 执行全部 001-010
# uv run python apply_migrations.py 009    # 仅执行 009（用户隔离）
# uv run python apply_migrations.py 010    # 仅执行 010（积分计费）
```

脚本从 `DATABASE_URL` 取连接信息，无需额外配置密码；幂等，可重复执行。执行 `009` 前需保证应用至少成功启动过一次（已建 `users` 表并播种管理员），因为 `009` 要把历史数据回填给管理员。`010` 幂等且无前置数据依赖，可在 `009` 之后任意时机执行。

### 4. 升级已有环境

线上环境数据库已运行、但尚未执行 `001-010` 时（典型升级场景），步骤如下：

1. 构建并推送含最新代码与 `apply_migrations.py` 的镜像。
2. SAE 部署新镜像——应用启动时 `create_all` 补建缺失的表，并按需播种管理员。
3. 进入容器执行 `uv run python apply_migrations.py`，补齐 `001-010`（重点 `009` 的 `user_id` 用户隔离、`010` 的积分计费表与回填）。
4. 验证：管理员可登录；业务表已含 `user_id` 列；历史数据已回填给管理员；`user_points` / `point_transactions` 表存在。

> 多实例并发：`001-010` 设计为幂等（先探测列/约束是否存在再执行 DDL），重复执行安全。若多实例同时启动并各自执行迁移，偶发竞争重跑一次脚本即可恢复。

### 5. 验证

```bash
curl -f http://<线上域名>/health      # 预期 200
```

并在前端完成管理员登录，确认用户管理、图片/视频生成等功能正常。

### 6. 积分计费配置

积分计费依赖 Redis（账户锁），**生产环境必须部署 Redis**——锁层在 Redis 不可用时不会降级为无操作，抢锁会直接失败。本地开发使用 Docker Compose 提供的 Redis 即可。

以下配置项均可在 `backend/.env` 或环境变量中覆盖，默认值适用于绝大多数场景：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `POINTS_QUOTE_EXPIRE_SECONDS` | `300` | 报价令牌有效期（秒）。令牌过期后前端需重新报价 |
| `POINTS_LOCK_TTL_MS` | `30000` | Redis 用户锁 TTL（毫秒），覆盖一次完整的账户变更 |
| `POINTS_LOCK_WAIT_MS` | `3000` | 抢锁等待上限（毫秒），超时抛 `PointsOperationBusyError` |
| `POINTS_LOCK_RETRY_MAX_BACKOFF_MS` | `250` | 抢锁指数退避上限（毫秒） |
| `POINTS_RECONCILE_MIN_AGE_SECONDS` | `1800` | 对账扫描的最小冻结年龄（秒），冻结超过该年龄且未结算才会被兜底处理 |
| `POINTS_RECONCILE_BATCH_SIZE` | `100` | 对账单批扫描上限，控制单次 Beat tick 的 DB 负载 |

> 这些项通常无需调整；调高 `POINTS_LOCK_WAIT_MS` 可在高并发账户变更时减少 `PointsOperationBusyError`，但也会拉长最坏情况下的请求耗时。

## OpenAPI 客户端同步

Backend API 发生变化后，先启动 Backend，再同步 Frontend generated client：

```bash
cd front
pnpm run openapi:update
pnpm exec tsc --noEmit
```

Frontend 调用 Backend API 时应使用 `front/src/services/generated/` 中的 OpenAPI generated client。

## License

本项目使用 [Apache-2.0](./LICENSE) 许可证。
