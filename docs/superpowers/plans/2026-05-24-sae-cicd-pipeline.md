# SAE CI/CD 自动化部署流水线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 GitHub Actions 流水线，将 Jellyfish 应用（前端 + 后端 + Celery Worker）打包为单一 Docker 镜像，自动部署到阿里云 SAE；删除已过时的 GHCR 推送 workflow。

**Architecture:** 多阶段 Dockerfile（combined.Dockerfile）先用 Node 构建前端产物，再打入 Python 后端镜像；supervisord 在同一容器内同时管理 uvicorn（Web + API）和 celery worker 两个进程；FastAPI 通过 StaticFiles 直接 serve 前端静态文件，前后端同源无跨域问题。

**Tech Stack:** Docker multi-stage build、supervisord、GitHub Actions、阿里云 ACR、阿里云 SAE、aliyun CLI、FastAPI StaticFiles、Python 3.12、Node 20、pnpm 9.15.9

---

## 文件清单

| 操作 | 路径 | 职责 |
|---|---|---|
| 新增 | `deploy/docker/supervisord.conf` | 管理 uvicorn + celery worker 两个进程 |
| 新增 | `deploy/docker/combined.Dockerfile` | 多阶段构建：前端 → 后端 + dist + supervisord |
| 修改 | `backend/app/main.py` | 在 API 路由后挂载 StaticFiles，serve 前端 |
| 新增 | `.github/workflows/deploy-prod.yml` | 生产流水线：`v*` tag 触发，构建推 ACR + 部署 SAE |
| 新增 | `.github/workflows/deploy-test.yml` | 测试流水线：`test` 分支触发，构建推 ACR + 部署 SAE |
| 删除 | `.github/workflows/ghcr-images.yml` | 旧 GHCR 推送流程，已被 ACR 替代 |

---

## Task 1：创建 supervisord.conf

**Files:**
- Create: `deploy/docker/supervisord.conf`

- [ ] **Step 1: 创建 supervisord.conf**

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

说明：
- `nodaemon=true`：supervisord 前台运行，符合容器最佳实践
- `logfile=/dev/null`：supervisord 自身日志丢弃，各子进程日志直接输出到 stdout/stderr，与 SAE 日志采集兼容
- 两个进程均设 `autorestart=true`，任一崩溃后自动重启

- [ ] **Step 2: Commit**

```bash
git add deploy/docker/supervisord.conf
git commit -m "[ci] 添加 supervisord.conf，管理 web+worker 进程"
```

---

## Task 2：创建 combined.Dockerfile

**Files:**
- Create: `deploy/docker/combined.Dockerfile`
- Reference: `deploy/docker/backend.Dockerfile`（复用后端构建逻辑）
- Reference: `deploy/docker/front.Dockerfile`（复用前端构建逻辑）

- [ ] **Step 1: 创建 combined.Dockerfile**

创建 `deploy/docker/combined.Dockerfile`，内容如下：

```dockerfile
# ── Stage 1: 构建前端 ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app

RUN corepack enable
RUN corepack prepare pnpm@9.15.9 --activate

COPY front/package.json front/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY front/ ./

# 构建参数：前端 API baseURL，默认走相对路径 /api/v1（与后端同源）
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN pnpm run build


# ── Stage 2: 后端 + 前端产物 + supervisord ────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/root/.cache/uv

WORKDIR /app

# 安装系统依赖：supervisor 用于多进程管理
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl supervisor \
  && rm -rf /var/lib/apt/lists/*

# 安装 uv（Python 包管理器）
RUN pip install --no-cache-dir uv

# 优先 COPY 依赖文件，利用 Docker 层缓存
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# COPY 后端源码
COPY backend/ ./
RUN uv sync --frozen --no-dev

# COPY 前端构建产物（由 Stage 1 生成的 dist/）
COPY --from=frontend-build /app/dist ./dist

# COPY supervisord 配置
COPY deploy/docker/supervisord.conf /etc/supervisor/supervisord.conf

EXPOSE 8000

CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
```

- [ ] **Step 2: 在本地验证镜像可以构建（不含运行时依赖）**

在项目根目录执行（需要 Docker 环境）：

```bash
docker build -f deploy/docker/combined.Dockerfile -t jellyfish-combined:local .
```

预期输出：最后一行为 `Successfully built <image-id>` 或 `writing image sha256:...`，无报错。

验证镜像内文件结构：

```bash
docker run --rm jellyfish-combined:local ls -la /app/dist
docker run --rm jellyfish-combined:local ls /etc/supervisor/supervisord.conf
```

预期：`dist/` 存在且包含 `index.html`、`assets/` 等前端产物；`supervisord.conf` 存在。

- [ ] **Step 3: Commit**

```bash
git add deploy/docker/combined.Dockerfile
git commit -m "[ci] 添加 combined.Dockerfile（前后端+supervisord 合并镜像）"
```

---

## Task 3：修改 main.py，挂载前端静态文件

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_response_envelopes.py`（验证现有 API 测试不受影响）

- [ ] **Step 1: 确认现有 API 测试通过（基准）**

```bash
cd /path/to/project
uv run --directory backend pytest tests/test_api_response_envelopes.py -v
```

预期：所有测试 PASS。

- [ ] **Step 2: 修改 backend/app/main.py，在文件末尾追加 StaticFiles 挂载**

在 `health` 函数定义之后，文件末尾追加以下内容：

```python
# 生产环境：serve 前端静态文件（dist/ 存在时自动挂载）
# 本地纯后端开发时 dist/ 不存在，条件跳过，不影响开发体验
from pathlib import Path
from fastapi.staticfiles import StaticFiles as _StaticFiles

_dist_dir = Path(__file__).resolve().parent.parent / "dist"
if _dist_dir.exists():
    app.mount("/", _StaticFiles(directory=str(_dist_dir), html=True), name="frontend")
```

说明：
- `Path(__file__).resolve().parent.parent`：`main.py` 在 `app/`，`parent.parent` 即 `/app`（容器工作目录），指向 `dist/`
- `html=True`：未匹配到静态文件时返回 `index.html`，支持 React Router 的客户端路由
- API 路由（`/api/v1/*`、`/health`、`/docs`、`/redoc`）均在此之前注册，FastAPI 优先匹配已注册路由，不会被 StaticFiles 拦截
- 以 `_` 前缀导入避免与其他模块命名冲突

- [ ] **Step 3: 确认现有 API 测试仍然通过**

```bash
uv run --directory backend pytest tests/test_api_response_envelopes.py -v
```

预期：所有测试 PASS（`dist/` 在测试环境中不存在，挂载被跳过，不影响任何 API 路由）。

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "[feat] main.py 挂载前端静态文件（dist/ 存在时生效）"
```

---

## Task 4：创建生产部署 workflow（deploy-prod.yml）

**Files:**
- Create: `.github/workflows/deploy-prod.yml`
- Reference: `Toonflow-app/.github/workflows/docker.yml`（复用阿里云 CLI 安装、ACR 清理、SAE 部署逻辑）

- [ ] **Step 1: 创建 .github/workflows/deploy-prod.yml**

```yaml
name: Build and Deploy (Production)

on:
  push:
    tags:
      - "v*"
  workflow_dispatch:

jobs:
  docker:
    runs-on: ubuntu-latest
    name: 构建并部署生产镜像

    permissions:
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: 获取版本号
        id: version
        run: |
          echo "tag=${GITHUB_REF_NAME}" >> $GITHUB_OUTPUT

      - name: 设置 Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: 登录 ACR
        uses: docker/login-action@v3
        with:
          registry: crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      - name: 安装 aliyun CLI
        run: |
          curl -sLo /tmp/aliyun-cli.tgz https://aliyuncli.alicdn.com/aliyun-cli-linux-latest-amd64.tgz
          tar -xzf /tmp/aliyun-cli.tgz -C /tmp
          sudo mv /tmp/aliyun /usr/local/bin/aliyun

      - name: 构建并推送镜像
        uses: docker/build-push-action@v6
        with:
          context: .
          file: deploy/docker/combined.Dockerfile
          platforms: linux/amd64
          push: true
          tags: |
            crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish:${{ steps.version.outputs.tag }}
            crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: 清理 ACR 旧版本 tag（保留最新 3 个 v* tag）
        env:
          ALIBABACLOUD_ACCESS_KEY_ID: ${{ secrets.ALIYUN_ACR_AK_ID }}
          ALIBABACLOUD_ACCESS_KEY_SECRET: ${{ secrets.ALIYUN_ACR_AK_SECRET }}
          ALIBABACLOUD_REGION_ID: ${{ vars.SAE_REGION_ID }}
        run: |
          if [ -z "$ALIBABACLOUD_ACCESS_KEY_ID" ]; then
            echo "ALIYUN_ACR_AK_ID 未配置，跳过 ACR tag 清理"
            exit 0
          fi

          TAGS_JSON=$(aliyun cr GetRepoTags \
            --RepoNamespace fzzs \
            --RepoName jellyfish 2>/dev/null || echo '{"data":{"tags":[]}}')

          TAGS_TO_DELETE=$(echo "$TAGS_JSON" | \
            jq -r '.data.tags[] | select(.tag | test("^v")) | [.imageCreate, .tag] | @tsv' 2>/dev/null | \
            sort -t$'\t' -k1 -rn | \
            awk 'NR>3 {print $2}')

          if [ -z "$TAGS_TO_DELETE" ]; then
            echo "无需清理（v* tag 数量 ≤ 3）"
          else
            for TAG in $TAGS_TO_DELETE; do
              echo "删除旧 tag: $TAG"
              aliyun cr DeleteRepoTag \
                --RepoNamespace fzzs \
                --RepoName jellyfish \
                --Tag "$TAG" || echo "警告：删除 $TAG 失败，继续"
            done
            echo "清理完成"
          fi

      - name: 部署到 SAE 生产应用
        env:
          ALIBABACLOUD_ACCESS_KEY_ID: ${{ secrets.ALIYUN_SAE_AK_ID }}
          ALIBABACLOUD_ACCESS_KEY_SECRET: ${{ secrets.ALIYUN_SAE_AK_SECRET }}
          ALIBABACLOUD_REGION_ID: ${{ vars.SAE_REGION_ID }}
          SAE_PROD_APP_ID: ${{ secrets.SAE_PROD_APP_ID }}
        run: |
          if [ -z "$SAE_PROD_APP_ID" ]; then
            echo "SAE_PROD_APP_ID 未配置，跳过生产部署"
            exit 0
          fi

          aliyun sae DeployApplication \
            --AppId "$SAE_PROD_APP_ID" \
            --ImageUrl "crpi-7ajeyduewy90avu4-vpc.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish:${{ steps.version.outputs.tag }}"

          echo "SAE 生产环境部署已触发，请在控制台确认发布状态"
          echo "镜像：crpi-7ajeyduewy90avu4-vpc.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish:${{ steps.version.outputs.tag }}"
```

注意：
- `--ImageUrl` 使用 VPC 内网地址（`-vpc` 后缀），SAE 从 ACR 拉镜像走内网，与 Toonflow 保持一致
- `SAE_PROD_APP_ID` 未配置时跳过部署而非报错，便于在 secrets 就绪前先验证镜像构建步骤

- [ ] **Step 2: 校验 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-prod.yml'))" && echo "YAML OK"
```

预期输出：`YAML OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-prod.yml
git commit -m "[ci] 添加生产环境部署 workflow（v* tag 触发）"
```

---

## Task 5：创建测试部署 workflow（deploy-test.yml）

**Files:**
- Create: `.github/workflows/deploy-test.yml`
- Reference: `Toonflow-app/.github/workflows/docker-test.yml`

- [ ] **Step 1: 创建 .github/workflows/deploy-test.yml**

```yaml
name: Build and Deploy (Test)

on:
  push:
    branches:
      - test
  workflow_dispatch:

jobs:
  docker:
    runs-on: ubuntu-latest
    name: 构建并部署测试镜像

    permissions:
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: 设置 Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: 登录 ACR
        uses: docker/login-action@v3
        with:
          registry: crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      - name: 安装 aliyun CLI
        run: |
          curl -sLo /tmp/aliyun-cli.tgz https://aliyuncli.alicdn.com/aliyun-cli-linux-latest-amd64.tgz
          tar -xzf /tmp/aliyun-cli.tgz -C /tmp
          sudo mv /tmp/aliyun /usr/local/bin/aliyun

      - name: 构建并推送测试镜像
        uses: docker/build-push-action@v6
        with:
          context: .
          file: deploy/docker/combined.Dockerfile
          platforms: linux/amd64
          push: true
          tags: crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish:test
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: 部署到 SAE 测试应用
        env:
          ALIBABACLOUD_ACCESS_KEY_ID: ${{ secrets.ALIYUN_SAE_AK_ID }}
          ALIBABACLOUD_ACCESS_KEY_SECRET: ${{ secrets.ALIYUN_SAE_AK_SECRET }}
          ALIBABACLOUD_REGION_ID: ${{ vars.SAE_REGION_ID }}
          SAE_TEST_APP_ID: ${{ secrets.SAE_TEST_APP_ID }}
        run: |
          if [ -z "$SAE_TEST_APP_ID" ]; then
            echo "SAE_TEST_APP_ID 未配置，跳过测试部署"
            exit 0
          fi

          aliyun sae DeployApplication \
            --AppId "$SAE_TEST_APP_ID" \
            --ImageUrl "crpi-7ajeyduewy90avu4-vpc.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish:test"

          echo "SAE 测试环境部署已触发，请在控制台确认发布状态"
```

- [ ] **Step 2: 校验 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-test.yml'))" && echo "YAML OK"
```

预期输出：`YAML OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-test.yml
git commit -m "[ci] 添加测试环境部署 workflow（test 分支触发）"
```

---

## Task 6：删除 ghcr-images.yml

**Files:**
- Delete: `.github/workflows/ghcr-images.yml`

- [ ] **Step 1: 删除文件**

```bash
git rm .github/workflows/ghcr-images.yml
```

- [ ] **Step 2: Commit**

```bash
git commit -m "[ci] 删除 GHCR 镜像推送 workflow（已由 ACR+SAE 流水线替代）"
```

---

## Task 7：端到端验证

本 Task 无代码改动，仅验证流程。

- [ ] **Step 1: 确认全量后端测试通过**

```bash
uv run --directory backend pytest -v
```

预期：所有测试 PASS（StaticFiles 挂载在无 `dist/` 的测试环境中被跳过，不影响任何 API 测试）。

- [ ] **Step 2: 在 GitHub 仓库配置必要的 Secrets**

进入 GitHub 仓库 → Settings → Secrets and variables → Actions，新增以下 **Repository secrets**：

| Secret 名 | 值来源 |
|---|---|
| `SAE_PROD_APP_ID` | 阿里云 SAE 控制台 → 生产应用详情页的应用 ID |
| `SAE_TEST_APP_ID` | 阿里云 SAE 控制台 → 测试应用详情页的应用 ID |

以下为**组织级 Secrets**（已在 Toonflow 中配置，Jellyfish 仓库需被授权访问）：

| Secret/Var | 说明 |
|---|---|
| `ACR_USERNAME` | ACR 登录用户名 |
| `ACR_PASSWORD` | ACR 登录密码 |
| `ALIYUN_ACR_AK_ID` | 清理旧 tag 的 AK |
| `ALIYUN_ACR_AK_SECRET` | 清理旧 tag 的 SK |
| `ALIYUN_SAE_AK_ID` | 触发 SAE 部署的 AK |
| `ALIYUN_SAE_AK_SECRET` | 触发 SAE 部署的 SK |
| `vars.SAE_REGION_ID` | 区域 ID，如 `cn-shenzhen` |

确认方式：在 GitHub → Settings → Secrets → Actions → Organization secrets 中确认上述 secrets 已勾选允许本仓库访问。

- [ ] **Step 3: 触发测试流水线验证**

方式一（推荐先用）：在 GitHub Actions 页面手动触发 `Build and Deploy (Test)` workflow（workflow_dispatch）。

方式二：push 到 `test` 分支：

```bash
git checkout -b test
git push origin test
```

预期：Actions 页面中该 workflow 运行成功，ACR 中出现 `jellyfish:test` tag，SAE 测试应用触发滚动更新。

- [ ] **Step 4: 触发生产流水线验证**

打一个测试 tag：

```bash
git tag v0.1.0-rc1
git push origin v0.1.0-rc1
```

预期：`Build and Deploy (Production)` workflow 运行成功，ACR 中出现 `jellyfish:v0.1.0-rc1` 和 `jellyfish:latest` 两个 tag，SAE 生产应用触发滚动更新。
