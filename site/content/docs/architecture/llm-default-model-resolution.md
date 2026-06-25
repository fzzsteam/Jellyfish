---
title: "LLM 默认模型解析"
weight: 35
description: "当前生效的 LLM 默认模型来源与解析顺序。"
---

本文记录当前真实生效的默认模型规则（text / image / video）。

## 单一事实来源

- 默认模型统一由 `model_settings` 表维护：
  - `default_text_model_id`
  - `default_image_model_id`
  - `default_video_model_id`
- `models` 表不再承担“默认模型”语义，`models.is_default` 已下线。

> **每用户一行（自数据隔离改造起）**：`model_settings` 不再是“单表单行 id=1”的全局单例，而是**按 `user_id` 每用户一行**。读取/写入均按当前登录用户的 `user_id` 定位（无记录时惰性创建默认行）。详见 [用户数据隔离](../user-data-isolation/)。

## 解析规则

- 项目级文本整理调用优先读取 `projects.text_model_id`；为空时才回退到当前用户的 `model_settings.default_text_model_id`。
- 运行时按类别读取**当前用户**的 `model_settings` 行对应字段；生成任务执行时按任务归属用户（`generation_tasks.user_id`）解析。
- 若对应默认模型 ID 未配置，服务返回 `503`（`No default model configured for category=...`）。
- 若配置了模型 ID 但模型不存在，服务返回 `503`（`Configured default model not found: ...`）。

## 管理入口

- 默认模型仅通过 `LLM Model Settings` 接口维护（`/api/v1/llm/model-settings`）。
- 前端“模型管理”页面不再提供“设置”选项；模型选择改由资产编辑、分镜工作室等业务页面在发起生成时显式传入。
- 模型列表（`/api/v1/llm/models`）仅维护模型实体信息（名称、类别、供应商、参数等），不再提供默认切换语义。
