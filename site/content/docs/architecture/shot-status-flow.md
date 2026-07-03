---
title: "分镜状态流转说明"
description: "面向开发者说明 shot.status、skip_extraction、资产候选和对白候选的职责与流转规则。"
weight: 7
---

> 本文属于“当前架构”文档，描述当前已经生效的状态模型与后端判定规则。

## 背景

为了让“分镜是否具备生成视频条件”有统一、可追溯的判定来源，当前后端已经将 `shots.status` 收敛为**系统流程状态**，并引入两张候选表记录镜头提取确认过程中的中间状态。

这次调整的目标不是增加更多前端判断，而是把正式状态统一交给后端维护，前端只消费结果。

## 核心结论

- `shots.status`：信息提取确认状态，只由后端更新
- `shots.skip_extraction`：用户明确声明“当前镜头无需提取”
- `shot_extracted_candidates`：记录每一条资产提取候选项的处理状态
- `shot_extracted_dialogue_candidates`：记录每一条对白提取候选项的处理状态

也就是说：

```text
shots.status
  = 信息提取确认状态

skip_extraction
  = 是否跳过提取

shot_extracted_candidates
  = 资产候选的确认明细

shot_extracted_dialogue_candidates
  = 对白候选的确认明细
```

## `shot.status` 的语义

当前只保留两种正式状态：

- `pending`
  - 当前镜头还没有完成资产 / 对白等信息提取确认
- `ready`
  - 当前镜头的信息提取确认已经完成

这里的 `ready` 不再表示“看起来差不多了”，也不等于已经满足视频生成条件，而是明确表示：

> 当前分镜已经完成信息提取确认，可以进入后续生成准备检查。

视频生成条件由 `video-readiness` 单独判断，例如关键帧、参考图、视频参数等缺口不会写入 `shot.status`。

因此 UI 文案必须保持下面这条约束：

- `shot.status = ready`
  - 应显示为“提取确认完成”或“准备完成”
  - 不能直接翻译成“可生成视频”
- “可生成视频”
  - 必须来自 `video-readiness` 或明确的诊断结论

需要特别注意：

> 运行中的生成任务不再写入 `shots.status`。
> “生成中”应通过 `GenerationTask / GenerationTaskLink`
> 动态聚合得到，而不是复用 `pending / ready` 这类静态状态。

## `ready` 的判定规则

后端统一按以下规则重算：

1. 如果 `skip_extraction = true`，状态为 `ready`
2. 如果从未提取过，状态为 `pending`
3. 如果提取过但没有任何候选项，状态为 `ready`
4. 如果所有资产候选和对白候选都已经处理完，状态为 `ready`
5. 其他情况为 `pending`

其中“所有资产候选都处理完”指的是：

- `candidate_status = linked`
- 或 `candidate_status = ignored`

其中“所有对白候选都处理完”指的是：

- `candidate_status = accepted`
- 或 `candidate_status = ignored`

只要还有任意一条资产候选或对白候选处于 `pending`，镜头就不能进入 `ready`。

如果某个镜头提取后没有任何对白候选，这不会阻塞 `ready`。

当前分镜准备页只把角色、场景、道具作为需要用户确认的资产候选。`costume` 候选仍可保留在提取明细中，但不再计入 `asset_candidate_total` / `pending_asset_count`，也不会阻塞 `shot.status = ready`。

## `video-readiness` 与生成按钮

视频生成按钮必须由 `video-readiness` 结果控制，而不是由 `shot.status` 直接控制。

建议遵守以下前端规则：

- `shot.status = pending`
  - 直接提示继续做提取确认。
- `shot.status = ready` 且 `video-readiness` 仍有缺口
  - 允许展示“准备完成”，但按钮保持禁用或引导先补关键帧 / 参考图 / 参数。
- `shot.status = ready` 且 `video-readiness` 通过
  - 才展示为可发起视频生成。

诊断项展示时：

- 保留后端返回的英文 key，便于和契约、日志、调试信息对齐。
- 同时补充中文说明，解释用户还差什么。
- 不要把诊断项重新折叠回 `shot.status`。

## `shot_extracted_candidates` 表结构职责

这张表记录的是**镜头级资产提取确认明细**，而不是最终资产本身。

核心字段包括：

- `shot_id`
- `candidate_type`
  - `character / scene / prop / costume`
- `candidate_name`
- `candidate_status`
  - `pending / linked / ignored`
- `linked_entity_id`
- `source`
- `payload`
- `confirmed_at`

建议理解为：

```text
一条提取候选
→ 先进入 pending
→ 用户确认后变成 linked 或 ignored
```

## `shot_extracted_dialogue_candidates` 表结构职责

这张表记录的是**镜头级对白提取确认明细**。

核心字段包括：

- `shot_id`
- `index`
- `text`
- `line_mode`
- `speaker_name`
- `target_name`
- `candidate_status`
  - `pending / accepted / ignored`
- `linked_dialog_line_id`
- `source`
- `payload`
- `confirmed_at`

建议理解为：

```text
一条对白候选
→ 先进入 pending
→ 用户接受后写入 ShotDialogLine，并变成 accepted
→ 或用户明确忽略，变成 ignored
```

## 典型流转

### 路径 A：分镜提取后的自动准备

```text
script_divide
→ 写入章节分镜
→ 自动执行资产 / 对白提取
→ 有可用图片且高置信唯一匹配的资产候选自动 linked
→ 对白候选自动写入 ShotDialogLine 并 accepted
→ 缺图、低置信或多候选资产保留 pending
→ 全部资产候选和对白候选已 resolved 时
→ shot.status = ready
```

镜头详情的“提取确认”步骤负责处理自动准备后仍然 pending 的候选，或在需要修复时重新提取 / 刷新候选。
资产 / 对白提取会使用章节全文作为上下文；服务端优先使用任务 `run_args.script_text`，缺失时回退到章节 `condensed_text` / `raw_text`，最后才使用分镜摘录兜底。

### 路径 B：明确无需提取

```text
用户设置 skip_extraction = true
→ shot.status = ready
```

### 路径 C：取消关联 / 替换

```text
原 candidate = linked
→ 用户删除关联 / 替换关联对象 / 清空 scene
→ candidate 回退到 pending
→ shot.status 重新计算
```

## 已接入的自动回写点

当前后端已经接入这些回写动作：

- 提取接口完成后，按镜头同步 `shot_extracted_candidates`
- 提取接口完成后，按镜头同步 `shot_extracted_dialogue_candidates`
- 章节分镜提取任务完成写库后，会串行执行资产 / 对白提取与自动准备
- 自动准备会把已有可用图片且高置信唯一匹配的资产候选回写为 `linked`
- 自动准备会把对白候选写入 `ShotDialogLine` 并回写为 `accepted`
- 角色关联成功后，匹配角色候选回写为 `linked`
- 场景 / 道具关联成功后，匹配候选回写为 `linked`
- `ShotDetail.scene_id` 设置成功后，场景候选回写为 `linked`
- 删除场景 / 道具关联后，对应候选回退为 `pending`
- 同 index 角色被替换时，被顶掉的旧角色候选回退为 `pending`
- `scene_id` 从 A 切到 B，或清空时，旧场景候选回退为 `pending`
- 接受对白候选后，写入 `ShotDialogLine` 并将对白候选回写为 `accepted`
- 忽略对白候选后，将对白候选回写为 `ignored`

## 前端约束

前端页面现在必须遵守下面这条规则：

> 不再自行推导正式 `shot.status`，也不再手动把 `pending/ready` 写回本地状态。

正确做法是：

- 调后端接口
- 使用后端返回的最新 `ShotRead`
- 准备页优先消费后端聚合状态 `ShotPreparationState`
- 用 `shot_extracted_candidates` 展示资产待确认项
- 用 `shot_extracted_dialogue_candidates` 展示对白待确认项

当前分镜列表与镜头详情页已经按这套约束消费后端状态：`shot.status` 负责信息确认阶段，生成按钮与生成入口由 `video-readiness` 和诊断结果控制。

## OpenAPI 同步约定

这次改动新增了：

- `GET /api/v1/studio/shots/{shot_id}/preparation-state`
- `GET /api/v1/studio/shots/{shot_id}/extracted-candidates`
- `PATCH /api/v1/studio/shots/{shot_id}/skip-extraction`
- `PATCH /api/v1/studio/shots/extracted-candidates/{candidate_id}/link`
- `PATCH /api/v1/studio/shots/extracted-candidates/{candidate_id}/ignore`
- `GET /api/v1/studio/shots/{shot_id}/extracted-dialogue-candidates`
- `PATCH /api/v1/studio/shots/extracted-dialogue-candidates/{candidate_id}/accept`
- `PATCH /api/v1/studio/shots/extracted-dialogue-candidates/{candidate_id}/ignore`

前端在接口更新后，应主动执行：

```bash
cd front
pnpm run openapi:update
```

不要继续手写一层额外的 request 封装去复制 generated client。

## 准备页聚合状态约定

为了避免前端在“关联/忽略候选”之后自己猜测要刷新哪些局部状态，当前后端已经补了一层准备页聚合状态协议：

- 查询接口：
  - `GET /api/v1/studio/shots/{shot_id}/preparation-state`
- 准备页专用现有关联接口：
  - `POST /api/v1/studio/shots/{shot_id}/preparation-link`
- 聚合状态：
  - `shot`
  - `assets_overview`
  - `dialogue_candidates`
  - `saved_dialogue_lines`
  - `pending_confirm_count`
  - `ready_for_generation`

当前资源候选相关命令接口：

- `PATCH /api/v1/studio/shots/extracted-candidates/{candidate_id}/link`
- `PATCH /api/v1/studio/shots/extracted-candidates/{candidate_id}/ignore`
- `PATCH /api/v1/studio/shots/{shot_id}/skip-extraction`
- `PATCH /api/v1/studio/shots/extracted-dialogue-candidates/{candidate_id}/accept`
- `PATCH /api/v1/studio/shots/extracted-dialogue-candidates/{candidate_id}/ignore`

已经统一返回：

- `ShotPreparationMutationResult`
  - `action`
  - `state`

也就是说，准备页前端后续不应继续在这些动作成功后手写：

- `loadAssetsOverview()`
- `refreshCurrentShot()`
- 再自己拼 `pendingConfirmCount`

而应直接消费后端返回的最新聚合状态。

## 页面职责边界

随着 `shot.status`、候选确认链路和 `video-readiness` 的收口，分镜相关页面现在也有了更明确的职责边界。

### 分镜列表：章节镜头队列

这一页的核心任务是：

- 展示章节镜头队列与当前阶段
- 提供章节级批量生成、批量下载和批量诊断
- 把用户送到正确的单镜头详情步骤

### 镜头详情：单镜头主工作区

镜头详情按以下四个步骤组织：

```text
基础信息
→ 提取确认
→ 生成视频
→ 视频结果
```

其中前两个步骤负责准备，后两个步骤负责生成与回看。

凡是会直接影响：

- `skip_extraction`
- 资产候选 `pending / linked / ignored`
- 对白候选 `pending / accepted / ignored`
- `shot.status = pending / ready`

的动作，都应优先放在镜头详情的“基础信息 / 提取确认”步骤完成。

### 生成步骤与兼容 `/studio`

镜头详情“生成视频”步骤关注的是：

- 当前镜头能不能生成视频
- 还差哪些生成前置条件
- 先补关键帧、参考图还是视频参数

旧 `/studio` 路由当前只保留兼容跳转职责：

- 保证旧链接与旧回跳仍可使用
- 将用户落到当前镜头详情的生成相关步骤
- 不作为当前主流程入口

### 当前主流程

当前主流程如下：

```text
项目工作台（默认章节）
→ 分镜列表
→ 镜头详情
  → 基础信息
  → 提取确认
  → 生成视频
  → 视频结果
```

对应到页面职责上，就是：

- 分镜列表负责章节镜头队列与批量动作
- 镜头详情前两步负责“准备”
- 镜头详情后两步负责“生成与结果回看”

因此，生成相关页面里的提取确认状态更适合作为**诊断结果**或回跳入口，而不是重新承担主要确认动作。
