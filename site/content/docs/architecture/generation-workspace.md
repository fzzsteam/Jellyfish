# 生成准备架构

## 定位

Jellyfish 当前已经将多条生成链逐步收敛到统一的“生成准备”模型，用于解决以下问题：

- 基础真值与最终提交内容混用
- 预览与提交使用的上下文不一致
- 页面内部状态散落，`stale / loading / submit` 语义混乱

当前已接入该架构的链路包括：

1. 分镜帧图片生成
2. 视频提示词预览与提交
3. 资产图片生成（角色 / 演员 / 场景 / 道具 / 服装）

## 统一模型

当前统一使用 4 层结构：

1. `Base Draft`
   - 可持久化、可编辑的业务真值
2. `Context`
   - 本次生成依赖的动态上下文
3. `Derived Preview`
   - 基于 `Base Draft + Context` 推导出的预览结果
4. `Submission Payload`
   - 最终提交给模型的运行载荷

## 后端当前结构

当前统一服务目录位于：

```text
backend/app/services/studio/generation/
├── shared/
├── frame/
├── video/
└── asset_image/
```

### `shared`

负责放置生成准备的共享类型：

- `GenerationBaseDraft`
- `GenerationContext`
- `GenerationDerivedPreview`
- `GenerationSubmissionPayload`

### `frame`

当前关键帧图片链已经按以下职责拆分：

- `build_base`
- `build_context`
- `derive_preview`
- `build_submission`

当前 API 仍保持原路径不变，但内部已经开始调用这一层服务。

### `video`

当前视频链已经开始使用同样的四段式结构：

- `build_base`
- `build_context`
- `derive_preview`
- `build_submission`

当前 `preview-prompt` 与 `create video task` 已共享同一份 `reference_mode + images` 上下文。
镜头详情“生成视频”步骤中，参考模式为空表示未手动选择首帧 / 尾帧 / 关键帧模式；前端会以 `text_only` 作为后端契约值，并把第二步“资产与对白确认”中已确认资产的图片 file_id 放入 `images`，供提示词预览与视频生成任务共用。
视频任务提交给外部供应商时，若对象存储签出的“外部 URL”仍指向 `localhost`、回环地址或私网地址，后端会回退为 data URL，避免把供应商无法访问的本地 RustFS / MinIO 地址传给模型。
其中镜头详情当前使用的 `film/tasks/video/preview-prompt` 也会返回完整 `pack`：

- `previous_shot_summary`
- `next_shot_goal`
- `continuity_guidance`
- `composition_anchor`
- `screen_direction_guidance`
- `action_beats`
- `action_beat_phases`

因此镜头详情视频提示词预览与 studio 侧底层 pack 现在保持同源，不再出现“提示词有值但连续性上下文始终为空”的接口分叉。

当前视频参数已收口为以 `ratio` 为唯一业务主参数：

- 项目级默认：`Project.default_video_ratio`
- 分镜级覆盖：`ShotDetail.override_video_ratio`
- 前端在提交视频任务时显式传入本次生效的 `ratio`
- 后端直接使用请求中的 `ratio` 创建任务
- 若某个供应商不直接支持 `ratio`，由 provider adapter 在执行层内部派生辅助 `size`
- 前端比例枚举来自当前默认视频模型 capability 动态返回，不再使用静态常量
- 关键帧图片若用于视频参考，提交时会显式携带 `target_ratio + resolution_profile`
- 后端根据当前默认图片模型 capability 解析对应 `size`，保证关键帧画幅与目标视频保持一致
- 镜头详情会展示当前关键帧规格预览：`ratio + resolution_profile -> size`
- 视频提示词预览当前会额外暴露 `action_beats / previous_shot_summary / next_shot_goal / continuity_guidance`
- 视频提示词预览当前会额外暴露 `composition_anchor`
- 视频提示词预览当前会额外暴露 `screen_direction_guidance`
- `action_beats` 由当前镜头剧本摘录、镜头描述与对白规则化提炼，用于降低“像静态画面说明”的问题
- continuity 字段由相邻镜头摘要生成，用于降低镜头切换时的突兀感
- `composition_anchor` 由景别、运镜、主场景、主角色与相邻镜头关系规则化生成，用于降低构图和轴线突变
- `screen_direction_guidance` 由机位角度、对白关系、相邻镜头场景连续性规则化生成，用于降低人物翻面与反打跳轴
- 若视频模板未显式消费这些 guidance，系统会在模板渲染结果后自动补一段稳定的“镜头执行约束”，避免新字段只存在于 preview pack 中
- 即便视频走手动 prompt 分支，系统当前也会追加同一层 guidance 补强，避免手动文本完全绕过镜头连续性与构图约束
- 分镜帧 `frame-render-prompt` 当前也会把 `director_command_summary` 与必要的 `continuity_guidance` 轻量补入最终图片提示词
- 分镜帧 `frame-render-prompt` 当前也会把必要的 `frame_specific_guidance` 作为“当前帧职责”候选补入最终图片提示词
- 分镜帧 `frame-render-prompt` 当前也会把 `composition_anchor` 轻量补入最终图片提示词
- 分镜帧 `frame-render-prompt` 当前也会把 `screen_direction_guidance` 轻量补入最终图片提示词
  - 因此关键帧提示词预览中看到的高优先级导演约束，不再只停留在调试展示
  - 最终提交给图片模型的 render prompt 会显式带上这层收敛后的约束、当前帧职责、构图重心与朝向/视线要求
- 对于首帧，当前系统会优先强调“触发瞬间 / 初始反应 / 未完成态”表达，避免提示词直接落到后续完成动作或最终姿态
- 为避免 prompt 膨胀，这层收敛当前最多只保留 3 条 guidance
- 当前默认优先级为：`director_command_summary` > `continuity_guidance` > `screen_direction_guidance` > `composition_anchor`
- 这层优先级还会按 `frame_type` 做动态微调：
  - `first` 更偏向保留 `composition_anchor`
  - `key` / `last` 更偏向保留 `screen_direction_guidance`
  - 目的是让建立镜头先稳住空间，对峙/反打/收束镜头先稳住视线与左右轴线
- 前端关键帧提示词预览当前会直接展示：
  - “基础提示词生成依据”，用于说明 guidance 主要先服务于上游基础提示词生成
  - “最终图片提示词收敛结果”，用于说明只有少量 guidance 会被再次补进最终图片 prompt
  - 最终 render prompt 实际保留了哪些 guidance
  - 哪些 guidance 因压缩策略被舍弃
  - 每条 guidance 被保留或压缩的原因说明
  - 同时提供更短的 `reason_tag`，例如 `首帧保空间`、`关键帧保轴线`
  - 这样可以直接解释“为什么预览里有 4 条规则，但最终 prompt 只用了 3 条”
- 图片任务提交后，`render_context` 当前也会保留这组 guidance 决策详情
  - 因此任务链与预览链现在共享同一份“保留 / 压缩 / 原因”上下文
- 项目级信息提取当前还会输出镜头语言默认建议
  - `semantic_suggestion.camera_shot`
  - `semantic_suggestion.angle`
  - `semantic_suggestion.movement`
  - `semantic_suggestion.duration`
  - `semantic_suggestion.action_beats`
- `extract / extract-async` 在同步资产候选与对白候选之外，会按镜头序号将上述默认建议回写到 `ShotDetail`
  - 因此 `camera_shot / angle / movement / duration` 不再只依赖分镜写库时的硬编码初始值
  - `action_beats` 也会作为镜头动作拍点真值回写到 `ShotDetail`
  - 镜头详情中的镜头语言微调，修改的也是这同一份 `ShotDetail` 真值
- 分镜准备页聚合状态当前也会显式返回：
  - `basic_info_ready`
  - `semantic_defaults_ready`
  - `action_beats_ready`
  - `action_beats_count`
  - `action_beat_phases`
  - `ready_for_generation`
  - 其中 `ready_for_generation` 表示“准备页视角下可进入生成”，不等同于单纯的 `shot.status = ready`
- 视频链当前会优先消费 `ShotDetail.action_beats`
  - 只有在镜头尚未确认动作拍点时，才回退到基于 `script_excerpt + description + dialogue` 的规则化提炼
- 关键帧链当前也会优先消费 `ShotDetail.action_beats`
  - 后端会先对动作拍点做一层轻量 `trigger / peak / aftermath` 推断
  - 首帧优先消费触发阶段拍点
  - 关键帧优先消费峰值阶段拍点
  - 尾帧优先消费收束阶段拍点
- 视频 prompt 预览当前也会直接暴露这层阶段推断结果
  - 因此视频链与关键帧链现在会用同一套 `trigger / peak / aftermath` 标签来展示镜头内部动作过程

### `asset_image`

当前资产图片生成已开始迁移到：

- `build_base`
- `build_context`
- `derive_preview`
- `build_submission`

当前 actor / character / scene / prop / costume 图片的 render / submit 已开始走这套结构。

## 底层渲染组件约定

当前旧的图片兼容层已经移除，新的生成准备编排统一以以下目录为主入口：

- `generation/frame`
- `generation/video`
- `generation/asset_image`

其中仅保留 `shot_video_prompt_pack` 作为视频 pack 与模板渲染的底层组件：

- 它负责构建 `ShotVideoPromptPackRead`
- 它负责模板渲染所需的底层函数
- 它不再承担视频预览 / 提交的主编排入口职责

## 前端当前结构

### `useGenerationDraft`

当前前端已提供统一 hook：

```text
front/src/pages/aiStudio/hooks/useGenerationDraft.ts
```

该 hook 统一管理：

- `base`
- `context`
- `derived`
- `state`
- `deriveNow`
- `submitNow`
- `hydrate`
- `resetDerived`

### 当前已接入页面

#### 镜头详情

当前单镜头生成入口已经位于镜头详情页的“生成视频”步骤；章节镜头队列、批量动作与生成结果回看也已收口到分镜详情页内。生成准备架构在前端的主要落点是镜头详情“生成视频”：

- 单镜头 `video-readiness`
- 关键帧提示词预览
- 视频提示词预览
- 单镜头视频生成
- 批量生成、批量下载与批量诊断入口

其中镜头详情“生成视频”步骤当前已开始将：

- 关键帧提示词预览
- 视频提示词预览

当前单镜头 `video-readiness` 的职责是诊断和风险提示：它说明关键帧、参考图、参数或模型配置是否完整。
诊断未通过时，前端会提示用户存在风险并保留“诊断”入口，但不再把该结果作为进入视频提示词预览的唯一硬拦截。
硬拦截仍保留在基础必填项上，例如镜头时长、视频比例、视频模型和积分试算凭证。

接入 `useGenerationDraft`，逐步统一为：

- 用户编辑 `base`
- 页面维护 `context`
- 系统展示 `derived`
- 提交前通过 `submitNow()` 自动确保 `derived` 为最新结果

当前关键帧图片生成与视频生成都已经接入这套提交语义：

- 若基础提示词或上下文已变化，会先重新 `derive`
- 再使用最新的 `derived` 结果提交任务
- 页面不再单独维护一套“提交前再手动 render”的旁路逻辑

旧 `ChapterStudio` 页面已移除，`/studio` 路由当前仅保留兼容跳转说明：

- 兼容旧链接和旧回跳路径。
- 落点应回到当前镜头详情的相关生成步骤。
- 不再作为当前主入口或主要页面命名。

#### 资产编辑页

`AssetEditPageBase` 当前已开始将资产图片提示词预览与提交接入 `useGenerationDraft`。

因此，角色、演员、场景、道具、服装等资产编辑入口，已共享同一套生成准备心智模型。

其中，角色详情页也已收口到与演员 / 场景 / 道具 / 服装相同的资产编辑入口模型，不再单独维护一套角色图片生成入口逻辑。

当前资产图片生成提交也已统一为：

- 页面维护 `base + context`
- `submitNow()` 在提交前自动保证 `derived` 最新
- 任务创建使用最新的 `derived.prompt + derived.images`
- 调试信息默认收起，仅在用户主动展开时展示上下文与质量校验细节

资产编辑页的参考图来源已从描述框内的 `@` 提及机制迁移为独立的参考图管理区块：

- 用户可以从角色/演员/场景/道具/服装 5 种资产类型的资产库里选择其他资产的代表图作为参考图，支持拖拽排序、替换、移除。
- 参考图仅作为本次生成的临时候选，不写入任何资产关联关系，语义与镜头详情页关键帧生成的"临时参考图"一致。
- 生成前会调用 render-prompt 接口预览最终提示词与参考图组合，用户确认后才真正提交计费生成任务；render-prompt 接口已改为直接复用与提交任务相同的 `build_xxx_image_submission_payload` 逻辑，确保预览结果与实际生成完全一致。

## 当前边界

### 任务中心

任务中心保持“通用、轻量”的原则：

- 展示运行中、失败、取消、成功等任务状态，以及回跳入口
- 不承载业务级上下文摘要
- 不承载提示词调试详情

### 不属于该架构的模块

以下模块当前不属于“生成准备架构”：

1. 脚本处理类任务
2. 分镜编辑页的信息提取确认流
3. 任务中心

这些模块有独立职责，不参与当前的 `Base Draft / Context / Derived Preview / Submission Payload` 收敛。

## 视频供应商适配现状

当前视频生成执行层通过 `app/core/tasks/video_generation_tasks.py` 按 provider key 分派到具体供应商 adapter。

- `openai`、`volcengine`、`aliyun_bailian`、`vidu` 均已注册 `video_generation` 任务适配器。
- 阿里百炼 `happyhorse-1.1-r2v`（兼容旧 `happyhorse-1.0-r2v`）在单镜头视频生成时会自动收集当前分镜已关联的角色、场景、道具图片，作为多张 `reference_image` 传入；服装图片不再作为 r2v 视频参考图传入。
- `vidu` 视频生成走 `app/core/integrations/vidu/video.py`，使用 Vidu 官方 `POST /ent/v2/reference2video` 创建任务，并轮询 `GET /ent/v2/tasks/{task_id}/creations` 获取结果。
- Vidu 视频请求使用 `Authorization: Token {api_key}`，默认模型为 `viduq3`，参考帧与 r2v 资产参考图会映射为默认主题 `subject_1` 的 `subjects[0].images`。
- Vidu 非主体模型 `viduq3-mix` 使用同一接口，但请求体改为顶层 `images` 列表，不传 `subjects` 与 `audio`，默认分辨率映射为 `720p`。
- Vidu 文生视频模型 `viduq3-pro` 在无参考帧时走 `POST /ent/v2/text2video`，请求体包含 `style=general`、`movement_amplitude=auto`、`off_peak=false`，默认分辨率映射为 `540p`。
- Vidu 图生视频模型 `viduq3-pro` 在存在参考帧时走 `POST /ent/v2/img2video`，只使用第一张参考图作为 `images[0]`，请求体包含 `audio=true`、`voice_id=professional_host`、`movement_amplitude=auto`、`off_peak=false`，分辨率为 `1080p`。
- Vidu 首尾帧生视频模型 `viduq3-pro` 在同时存在首帧和尾帧时走 `POST /ent/v2/start-end2video`，使用前两张参考图作为 `images`，请求体包含 `audio=true`、`off_peak=false`，分辨率为 `1080p`。
- Vidu 智能多帧模型 `viduq2-turbo` 走 `POST /ent/v2/multiframe`，使用第一张参考图作为 `start_image`，后续参考图映射为 `image_settings[*].key_image`，并复用当前视频提示词与时长填充每个关键帧段落，分辨率为 `1080p`。
- Vidu 场景特效模板通过模型名 `template:{template_name}` 触发，当前可将 `template:hugging` 配置为视频模型；执行时走 `POST /ent/v2/template`，请求体传 `template`、参考图 `images`、提示词 `prompt` 与可选 `seed`，不传普通 `model` 字段。
- Vidu 模板成片通过模型名 `story:{story_name}` 或 `template-story:{story_name}` 触发；执行时走 `POST /ent/v2/template-story`，请求体只传 `story` 与参考图 `images`，不传普通 `model` 字段，也不依赖提示词字段。
- Vidu 视频能力声明 `supports_watermark=False`，业务层不会向 Vidu 视频请求体传递 `watermark` 字段；当前视频生成统一以无水印为目标，只有供应商显式支持无水印参数时才传 `watermark=False`。
- Vidu 图片生成走 `app/core/integrations/vidu/images.py`，使用 `POST /ent/v2/reference2image` 创建任务，请求体包含 `model`、`images`、`prompt`、`seed`、`aspect_ratio`、`resolution` 与空字符串 `payload`，并轮询同一套 `/ent/v2/tasks/{task_id}/creations` 结果接口。
- `backend/sql/017-add-vidu-image-model.sql` 会补齐 `Vidu` provider 与 `viduq2` 图片模型；资产编辑页从模型管理的图片模型列表读取该模型，选中后提交的参考图会映射为 Vidu `images`，无参考图时以 `images: []` 兼容文生图。该模型基础单价为 1，沿用图片计价规则：`standard`/1K 为 1 积分，`high`/2K 为 2 积分。
