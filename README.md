# Jellyfish 本地开发环境

Jellyfish 是面向 AI 短剧生产的工作台。本文件说明如何在本地启动开发环境、执行数据库迁移并验证各项服务。

推荐采用混合开发模式：MySQL、Redis 和 RustFS 运行在 Docker 中，Backend、Celery Worker 和 Frontend 运行在宿主机，便于热更新和查看日志。

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

迁移脚本位于 `backend/sql/`。全新环境和从旧版本升级的环境都应按文件名顺序执行当前脚本；执行 `009` 前必须确保 Backend 已至少成功启动一次，以便创建并播种初始管理员。

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
