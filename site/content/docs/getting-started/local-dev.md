---
title: "本地开发"
weight: 2
description: "启动前后端并完成本地联调。"
---

## 推荐本地模式

推荐把**基础设施**交给 Docker，把**前后端代码**留在宿主机跑：

- MySQL
- Redis
- RustFS

这样可以同时保留环境一致性和热更新效率。

## 启动基础设施

先复制本地 compose 环境文件：

```bash
cp deploy/compose/.env.local.example deploy/compose/.env.local
```

再启动基础设施：

```bash
docker compose --env-file deploy/compose/.env.local -f deploy/compose/docker-compose.infra.yml up -d
```

如果你本机已经有进程占用 `3306` 或 `6379`，这套本地开发默认会把 MySQL 端口映射到 `3307`、Redis 端口映射到 `6380`，后端也会同步连接到对应端口。

## 启动后端

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 启动前端

```bash
cd front
pnpm install
pnpm dev
```

## 默认端口

- 前端：`http://localhost:7788`
- 后端：`http://localhost:8000`
- Swagger：`http://localhost:8000/docs`
- RustFS：`http://localhost:9000`
- RustFS Console：`http://localhost:9001`

## OpenAPI 更新

```bash
cd front
pnpm run openapi:update
```

## 官网与文档站本地预览

```bash
cd site
hugo mod tidy
hugo server --buildDrafts --disableFastRender
```

## 推荐的联调顺序

1. 启动基础设施，确认 MySQL、Redis、RustFS 都已就绪。
2. 启动后端，确认 `/docs` 和 `/health` 正常。
3. 启动前端，确认页面能访问并能请求后端。
4. 如果修改了接口定义，再执行 `openapi:update`。
5. 如果同时在维护官网，再单独启动 `site/` 预览。
