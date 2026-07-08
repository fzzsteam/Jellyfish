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
# 不设 BACKEND_URL，让 openapi.ts 的 BASE 为空串，走同源请求
ENV VITE_BACKEND_URL=""

RUN pnpm run build
# 覆盖 public/env.js 的本地开发默认值，生产走同源相对路径
RUN printf 'window.__ENV=window.__ENV||{};window.__ENV.BACKEND_URL="";\n' > ./dist/env.js


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

# SAE 单容器内按进程分类保留日志；supervisord 仍会通过 log-tail 转发到 stdout。
RUN mkdir -p \
  /var/log/jellyfish/supervisor \
  /var/log/jellyfish/web \
  /var/log/jellyfish/worker \
  /var/log/jellyfish/beat

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
