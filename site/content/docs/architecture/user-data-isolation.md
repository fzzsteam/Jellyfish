---
title: "用户数据隔离"
weight: 15
description: "业务数据按 user_id 严格隔离的当前实现：归属表、service 过滤、系统模板共享与生成任务穿透。"
---

本文记录当前真实生效的用户数据隔离实现。配套认证闭环见 `user-auth-foundation` 计划产物（JWT 双令牌 + `get_current_user`）。

## 归属模型

- `app/models/base.py` 的 `UserOwnedMixin` 提供统一的 `user_id` 外键列（`String(64)`，`ForeignKey("users.id", ondelete="CASCADE")`，NOT NULL，带索引）。
- 以下 10 张表挂 `UserOwnedMixin`、按用户**强归属**：`projects`、`actors`、`scenes`、`props`、`costumes`、`files`、`providers`、`models`、`generation_tasks`（外加 `model_settings`，见下）。
- `prompt_templates` 例外：`user_id` **可空**。`is_system=True` 的系统预置模板 `user_id` 为 NULL、**全用户共享**；普通模板归属创建者。
- `model_settings` 例外：由“单表单行 id=1”改为**每 `user_id` 一行**（`uq_model_settings_user` 唯一约束）；读写按当前用户 upsert。
- **间接隔离**：`characters`、`shots`、`chapters`、各 `*_links`、`file_usages` 等子表不单独加 `user_id`，通过父实体（`project_id → projects.user_id` / `file_id → files.user_id`）间接隔离。

## 隔离的执行位置

隔离逻辑**只在 service 层**，路由层仅注入 `current_user` 并透传 `user_id=current_user.id`，不写任何过滤条件。

- 列表查询：`select(Model).where(Model.user_id == user_id)`。
- 单条 get/update/delete：取出后校验归属，不符按“未找到”处理（`entity_not_found`），避免泄露他人资源存在性。
- 资产名唯一性按用户：`actors`/`scenes`/`props`/`costumes` 的唯一约束为 `(user_id, name)`，不同用户可同名。
- 提示词模板查询放行系统模板：`where(or_(PromptTemplate.user_id == user_id, PromptTemplate.is_system.is_(True)))`；系统模板的“禁止删改”行为保留。

## 生成任务的 user_id 穿透

- 任务创建：路由的 `current_user.id` 沿 `路由 → service → TaskManager` 透传，写入 `generation_tasks.user_id`（`TaskRecord.user_id`）。
- 任务执行：执行器从任务记录的 `user_id` 读取该用户的 provider / model / `model_settings` 与默认提示词模板（resolver/runtime 均接收 `user_id` 参数，不再读全局单例）。
- 任务查询：任务列表/详情/取消按 `user_id` 过滤，用户只能看到并操作自己的任务。

## 历史数据与迁移

- 新建库由 `init_db()` 的 `create_all` 直接生成带 `user_id` 的完整表结构。
- 存量库由 `backend/sql/009-add-users-and-user-isolation.sql`（幂等）处理：逐表加列 → 回填初始管理员 → 收紧 NOT NULL + FK + 索引；并把资产旧的 `uq_<table>_name` 唯一约束替换为 `(user_id, name)`。系统提示词模板保持 `user_id = NULL`。
- 执行顺序：`create_all` → `seed_initial_admin()` → 部署脚本执行 `sql/009`。
