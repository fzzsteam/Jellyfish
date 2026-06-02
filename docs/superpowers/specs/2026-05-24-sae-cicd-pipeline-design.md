# SAE 自动化部署流水线设计

**日期：** 2026-05-24
**状态：** 待实施

---

## 背景

Jellyfish 当前已有推送到 GHCR 的镜像构建流水线（`ghcr-images.yml`），但没有自动化部署能力。本设计目标是新增 GitHub Actions 流水线，将应用自动构建并部署到阿里云 SAE（Serverless App Engine），同时删除已不再需要的 GHCR 推送 workflow。

参考同组织下 Toonflow 项目（`fzzsteam/Toonflow-app`）的 `docker.yml` 和 `docker-test.yml`，复用已有的组织级 Secrets。

---

## 目标

- `test` 分支 push → 自动构建并部署到测试环境
- `v*` tag push → 自动构建并部署到生产环境
- 前端、后端 API、Celery Worker 合并为单一镜像，运行在同一 SAE 应用中
- 复用组织级阿里云 Secrets，不引入额外凭证

---

## 核心决策

### 单镜像合并前后端

前端（React/Vite）构建产物 `dist/` 通过多阶段 Dockerfile 打包进后端（Python/FastAPI）镜像，由 FastAPI 的 `StaticFiles` 直接 serve 静态文件。

**选择原因：**
- 单一镜像对应单一 SAE 应用，运维最简单
- FastAPI 已有路由优先机制，`/api/v1/*` 不会被静态文件拦截
- 无需 Nginx 反向代理、无需 ALB 路径路由配置
- 前后端同源，无跨域问题

**不需要 Nginx 的原因：** FastAPI（uvicorn）直接 serve 静态文件和 API，SAE 只需暴露 8000 端口。

### Celery Worker 合并进同一容器（supervisord）

使用 supervisord 在同一容器内同时运行 uvicorn（Web + API）和 celery worker，对应同一个 SAE 应用。

**选择原因：**
- SAE 只需维护 1 个应用（prod）+ 1 个应用（test），无需额外 worker 应用
- 当前规模下 web 和 worker 资源需求一致，独立扩缩容意义不大
- 部署流程更简单，secrets 更少
- supervisord 负责各进程崩溃后的自动重启

### 删除 GHCR 流水线

`ghcr-images.yml` 构建两个独立镜像推送 GHCR，与新方案（单镜像推 ACR）冲突且冗余，直接删除。

---

## 镜像仓库

**ACR 地址（复用 Toonflow 同账号下的不同仓库）：**

```
crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish
```

| Tag | 触发条件 | 用途 |
|---|---|---|
| `v1.2.3` / `latest` | `v*` tag | 生产环境 |
| `test` | `test` 分支 | 测试环境 |

---

## 文件改动清单

### 新增

| 文件 | 说明 |
|---|---|
| `deploy/docker/combined.Dockerfile` | 多阶段构建：Node 构建前端 → Python 后端 + dist/ + supervisord |
| `deploy/docker/supervisord.conf` | supervisord 配置：同时管理 uvicorn 和 celery worker |
| `.github/workflows/deploy-prod.yml` | 生产部署：`v*` tag 触发 |
| `.github/workflows/deploy-test.yml` | 测试部署：`test` 分支触发 |

### 修改

| 文件 | 改动 |
|---|---|
| `backend/app/main.py` | API 路由注册后挂载 `StaticFiles(directory="dist")` |

### 删除

| 文件 | 原因 |
|---|---|
| `.github/workflows/ghcr-images.yml` | 被 ACR+SAE 流水线替代 |

### 保留不动

`backend-pylint.yml`、`commit-messages.yml`、`tag-release.yml`、`backend.Dockerfile`、`front.Dockerfile`

---

## combined.Dockerfile 结构

```dockerfile
# Stage 1: 构建前端
FROM node:20-alpine AS frontend-build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
COPY front/package.json front/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY front/ ./
ARG VITE_API_BASE_URL=/api/v1
RUN pnpm run build

# Stage 2: 后端 + 前端产物 + supervisord
FROM python:3.12-slim
# 安装 supervisord
RUN apt-get update && apt-get install -y --no-install-recommends supervisor && rm -rf /var/lib/apt/lists/*
# ... 安装后端依赖（同 backend.Dockerfile）
COPY --from=frontend-build /app/dist ./dist
COPY deploy/docker/supervisord.conf /etc/supervisor/conf.d/jellyfish.conf
EXPOSE 8000
CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
```

构建参数 `VITE_API_BASE_URL=/api/v1` 使前端 API 请求走相对路径，与后端同源。

## supervisord.conf 结构

```ini
[supervisord]
nodaemon=true
logfile=/dev/null
logfile_maxbytes=0

[program:web]
command=uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:worker]
command=uv run celery -A app.core.celery_app:celery_app worker -l info
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

日志直接输出到 stdout/stderr，与 SAE 日志采集兼容。

---

## main.py 改动

在所有路由注册完成后追加：

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

dist_dir = Path(__file__).parent.parent / "dist"
if dist_dir.exists():
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
```

条件判断确保本地纯后端开发时不受影响（`dist/` 不存在时跳过）。

---

## workflow 设计

### deploy-prod.yml（生产）

**触发：** `push` to `v*` tags 或 `workflow_dispatch`

**步骤：**
1. Checkout
2. 设置 Docker Buildx
3. 登录 ACR（`ACR_USERNAME` / `ACR_PASSWORD`）
4. 安装 aliyun CLI
5. 构建并推送镜像（tag: `v*` + `latest`，`linux/amd64`，GHA cache）
6. 清理 ACR 旧版本 tag（保留最新 3 个 `v*` tag）
7. 部署应用到 SAE（`SAE_PROD_APP_ID`，容器内同时运行 web + worker）

### deploy-test.yml（测试）

**触发：** `push` to `test` 分支 或 `workflow_dispatch`

**步骤：**
1. Checkout
2. 设置 Docker Buildx
3. 登录 ACR
4. 安装 aliyun CLI
5. 构建并推送镜像（tag: `test`）
6. 部署应用到 SAE（`SAE_TEST_APP_ID`，容器内同时运行 web + worker）

---

## Secrets 配置

### 组织级（已有，无需新增）

| Secret / Var | 用途 |
|---|---|
| `ACR_USERNAME` | ACR 登录用户名 |
| `ACR_PASSWORD` | ACR 登录密码 |
| `ALIYUN_ACR_AK_ID` | 清理旧 ACR tag 的 AccessKey ID |
| `ALIYUN_ACR_AK_SECRET` | 清理旧 ACR tag 的 AccessKey Secret |
| `ALIYUN_SAE_AK_ID` | 触发 SAE 部署的 AccessKey ID |
| `ALIYUN_SAE_AK_SECRET` | 触发 SAE 部署的 AccessKey Secret |
| `vars.SAE_REGION_ID` | 阿里云区域（如 `cn-shenzhen`） |

### 本仓库新增

| Secret | 说明 |
|---|---|
| `SAE_PROD_APP_ID` | 生产环境 SAE App ID |
| `SAE_TEST_APP_ID` | 测试环境 SAE App ID |

---

## SAE 应用配置

### 应用（prod / test，各一个）

| 配置项 | 值 |
|---|---|
| 镜像 | `crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish:<tag>` |
| 启动命令 | `supervisord -n -c /etc/supervisor/supervisord.conf` |
| 监听端口 | 8000 |
| 容器内进程 | web（uvicorn）+ worker（celery），由 supervisord 管理 |

### 环境变量（在 SAE 控制台配置）

**必填：**
```
DATABASE_URL=mysql+aiomysql://user:password@rds-host:3306/dbname
REDIS_HOST=r-xxx.redis.rds.aliyuncs.com
REDIS_PORT=6379
REDIS_PASSWORD=your-redis-password
S3_ENDPOINT_URL=https://oss-cn-shenzhen.aliyuncs.com
S3_ACCESS_KEY_ID=your-ak
S3_SECRET_ACCESS_KEY=your-sk
S3_BUCKET_NAME=your-bucket
```

**选填：**
```
S3_PUBLIC_BASE_URL=https://cdn.example.com
CORS_ORIGINS=https://example.com
DEBUG=false
```

---

## 保留的 workflow 说明

以下 workflow 与部署无关，继续保留：

| 文件 | 职责 |
|---|---|
| `backend-pylint.yml` | PR 代码质量检查 |
| `commit-messages.yml` | PR 提交格式校验 |
| `tag-release.yml` | `v*` tag 自动生成 GitHub Release 和 changelog |
