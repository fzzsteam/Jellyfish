# 镜头详情"提取确认"体验优化与关键帧面板迁移设计

## 背景

`docs/superpowers/specs/2026-07-02-project-shot-flow-redesign-design.md` 已经把主流程收敛为"镜头详情四步"（基础信息 / 提取确认 / 生成视频 / 视频结果），页面层级重构（项目列表、章节工作台默认页、镜头详情 4 Tab、旧分镜工作室跳转兼容）已经落地。

本设计是该改造的延续，聚焦用户在实际使用镜头详情页第 2 步（提取确认）和第 3 步（生成视频）时反馈的 5 个具体体验问题：

1. "提取确认"命名与内部资产/对白子模块命名不够贴切
2. 分镜列表每条镜头的状态徽标重复、冗余
3. 资产候选确认的"关联/新建"按钮（本次确认暂不改动，维持现状）
4. 对白确认只能通过提取生成，无法手动补录
5. 生成视频时提示缺少参考帧，但镜头详情页目前完全没有生成/关联参考帧的入口——因为该能力只存在于已废弃、无路由可达的 `ChapterStudio.tsx` 中，从未迁移到新页面

## 与 07-02 设计的关系（重要边界）

07-02 文档"生成模式与模型能力"一节定义的目标是：生成模式按视频模型能力过滤可见选项，且用户界面使用产品语言（首帧生成/首尾帧生成/参考图生成等）而非 `reference_mode` 技术 key。

**该目标尚未实现**：`VideoModelCapability`（`app/core/integrations/video_capabilities.py`）目前没有任何字段声明模型支持哪些参考模式，前端也没有任何模式选择 UI（`ChapterShotEditPage.tsx` 全部硬编码 `reference_mode: 'first'`）。近 30 条提交记录中也没有相关开发痕迹，此前"另找 agent 实现"的工作实际从未开始。

本设计**不实现**模型能力过滤和产品语言命名，而是先落地一个技术 key 的手动 Select（见下文"生成视频步骤：参考模式选择"），把"完全没有入口、生成必然卡住"的问题解决掉。模型能力过滤仍是后续独立工作，沿用 07-02 文档已定的目标，不在本设计中展开。

## 目标

- 修正"提取确认"步骤及其子模块命名，让文案匹配实际功能（资产关联、对白确认）
- 精简分镜列表每条镜头的状态展示，消除重复信息
- 让用户能在"对白确认"里手动补录对白，不必依赖提取
- 把关键帧/参考图生成与应用能力从已废弃的 `ChapterStudio.tsx` 迁移到镜头详情页"生成视频"步骤，采用适配新页面数据结构的实现（不逐行照搬），解除当前"参考帧缺失但无处可去"的阻塞
- 更新 `CLAUDE.md` 页面职责边界描述，反映分镜工作室已废弃、关键帧面板正在迁移的现状（已在本轮对话中完成，见"已完成的前置修改"）

## 非目标

- 不实现"生成模式按模型能力过滤 + 产品语言命名"（07-02 遗留目标，本设计明确搁置）
- 不改动资产候选确认卡片的"关联/新建"按钮逻辑（用户确认维持现状）
- 不删除 `ChapterStudio.tsx` 死代码（迁移完成、确认无依赖后再单独清理，不在本次范围）
- 不重做任务中心或批量诊断相关逻辑

## 已完成的前置修改

`CLAUDE.md` "页面职责边界" 一节已更新为：

- 镜头详情页承担准备 + 单镜头生成职责，四步流程展开说明
- 分镜工作室已废弃，`/studio` 路由只做跳转兼容，关键帧面板尚未迁移是已知缺口

## 设计详情

### 1. 命名调整

涉及文件：`front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`、`front/src/pages/aiStudio/shots/components/ChapterShotAssetConfirmation.tsx`

| 现状 | 调整为 |
|---|---|
| "2 提取确认"（`ChapterShotEditPage.tsx:2563`） | "2 资产与对白确认" |
| "2.1 资产候选确认"（`ChapterShotAssetConfirmation.tsx:300`） | "2.1 资产关联" |
| "2.2 对白确认"（`ChapterShotDialogueConfirmation.tsx:81`） | 不变 |

`CreationGuidePage.tsx` 中提到"提取确认"的引导文案（第 22/38/56/57/69/222/223/227 行）需要同步替换为"资产与对白确认"，保持指南与实际 UI 一致。

### 2. 分镜列表状态徽标合并

涉及文件：`front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`（`getExtractionListStatus`、`getShotPreparationIssueSummary`、列表渲染 `List` 的 `renderItem`，约 2916-3022 行）

现状：每条镜头渲染 3 个徽标——名称右侧 1 个（`itemIssueSummary`），名称下方 2 个（`基础已完成/基础待补` + `itemConfirmStatus`），语义重叠。

调整为 1 个徽标，放在名称右侧，去掉名称下方两个：

- 基础信息不完整 → "基础待补"（gold）
- 基础信息完整，但资产/对白候选仍有待处理项 → "待关联确认 N 项"（gold，N = 待处理资产候选数 + 待处理对白候选数之和）
- 全部完成 → "准备完成"（green）

实现上合并 `getShotPreparationIssueSummary` 的语义到一个函数即可，`getExtractionListStatus` 和名称下方的 `基础已完成/基础待补` 徽标渲染整体删除。

此调整只覆盖"步骤 1+2"的准备阶段状态，不反映"步骤 3 生成视频/步骤 4 视频结果"的状态（避免列表对每条镜头都拉取 video-readiness 造成性能开销）；步骤 3/4 状态仍只在打开单个镜头后，在对应 Tab 自己的标签里查看（如"生成视频"Tab 右上角"可生成/待补齐"）。

### 3. 资产候选确认按钮

维持现状不变。审查中发现的两个命名不一致问题（已关联卡片"新建"按钮实际是打开编辑页；解除关联按钮和候选卡片忽略按钮共用"忽略"文案）本次不处理，留待后续单独评估。

### 4. 对白手动新增

涉及文件：`front/src/pages/aiStudio/shots/components/ChapterShotDialogueConfirmation.tsx`

- 在标题行（"全部接受"/"全部忽略"按钮旁）新增"新增对白"按钮
- 点击后在 `savedDialogLines` 渲染列表末尾插入一行本地草稿行，样式与已保存行一致（说话人/对象/内容三个可编辑字段）
- 草稿行的 `text` 输入变为非空时，调用 `shot_dialogs.create()`（后端已支持，见 `backend/app/services/studio/shot_dialogs.py:71`，路由 `backend/app/api/v1/routes/studio/shots.py:645`）创建记录，创建成功后转为正式的已保存行（走 `onUpdateSavedDialogText` 更新路径）；若用户未输入内容就离开（blur 且为空），直接移除草稿行，不调用接口
- `index` 取当前已保存对白最大 `index + 1`
- `speaker_name`/`target_name` 为可选纯文本字段，不要求先创建角色实体

不需要新增后端接口或 OpenAPI 变更，`ShotDialogLineCreate` 已支持 `speaker_name`/`target_name` 纯文本（`backend/app/schemas/studio/shots.py:196-204`）。

### 5. 关键帧与参考图面板迁移

#### 5.1 面板位置与结构

涉及文件：新增/改造 `front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx`，新增子组件（例如 `ShotKeyframePanel.tsx`），迁移逻辑参考 `front/src/pages/aiStudio/chapter/ChapterStudio.tsx` 中"关键帧与参考图"相关代码（约 3717-5197 行：`keyframePromptDraft` / `generateKeyframeCard` / `applyCardImage` / `loadCardThumbs`），但按新页面数据结构重写，不整体照搬。

在"3 生成视频"步骤新增"关键帧与参考图"小节，包含：

- **参考模式 Select**：纯文字（`text_only`）/ 首帧参考（`first`）/ 尾帧参考（`last`）/ 关键帧参考（`key`）/ 首尾帧（`first_last`）/ 首尾+关键帧（`first_last_key`），对应后端 `REQUIRED_FRAMES_BY_MODE`（`backend/app/services/studio/shot_video_readiness.py:31-38`）已有的 6 种取值，本次不做模型能力过滤（见"与 07-02 设计的关系"）
- 选择某个模式后，下方动态只显示该模式需要的帧类型卡片（例如选"首尾帧"只显示"首帧"和"尾帧"两张卡片，选"纯文字"不显示任何卡片）
- 每张帧类型卡片包含：候选缩略图横向列表（复用 `loadCardThumbs` 逻辑，通过 `relation_type='shot_frame_image'` 查询任务生成的候选图）、"生成"按钮（打开生成弹窗）、"使用"标记（当前生效的 `file_id` 对应哪张）

视频生成请求提交的 `reference_mode` 直接使用用户在 Select 中选择的值（不做自动推导），对应帧的图片来源于该帧类型当前 `ShotFrameImage.file_id`。

#### 5.2 生成弹窗：参考图选择（自动 + 手动合一）

现状（`ChapterStudio.tsx`）用"自动收集已关联资产缩略图"（`autoKeyframeRefFileIds`，第 3846-3873 行）作为默认值，另外 4 个独立弹窗（角色/场景/道具/服装）供手动覆盖选择，代码复杂且强依赖旧页面级 state，不能直接复用。

新页面改为**一个统一弹窗**：

- 弹窗打开时，默认列出当前镜头第 2 步已关联的全部资产（`unionAssets` 中 `status === 'linked'` 的角色/场景/道具/服装项，每项自带 `file_id`），按类别分组展示，全部默认勾选——等价于旧页的自动收集效果，但直接复用步骤 2 已有的 `unionAssets` 数据，不需要另外维护一套关联状态
- 用户可以在同一弹窗内取消勾选不想用于本次融图的资产，也可以拖拽调整参考图顺序（对应旧页 `moveKeyframePromptRefFile` 的重排能力）
- 弹窗内可编辑生成提示词（复用 `keyframePromptDraft` / `useGenerationDraft` 模式，参照 `front/src/pages/aiStudio/hooks/useGenerationDraft.ts`）
- 确认后调用 `StudioImageTasksService.createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost` 创建生成任务，沿用现有轮询逻辑（间隔、次数与旧页一致）
- 生成完成后的候选图，点击"使用"调用 `StudioShotFrameImagesService.updateShotFrameImageApiV1StudioShotFrameImagesImageIdPatch` 设置为当前 `file_id`

不做的部分：旧页面里针对角色/场景/道具/服装分别打开独立弹窗手动搜索添加的能力——新弹窗里的资产候选来源仅限"第 2 步已关联的资产"，不支持在这个弹窗里额外搜索关联新资产（如需要更多资产参与融图，应回到第 2 步"资产关联"里先关联好）。

#### 5.3 与诊断的衔接

`VideoDiagnosticsDrawer`（`front/src/pages/aiStudio/shots/components/VideoDiagnosticsDrawer.tsx`）的 `reference_frames_ready` 检查项逻辑不变，本身已经能准确报告缺少哪个帧类型。用户根据检查项提示（如"缺少参考帧：first"）到新的"关键帧与参考图"小节里对应类型卡片生成/应用即可，不需要额外的诊断跳转链接。

## 数据与接口

不需要新增后端 API 或修改 OpenAPI：

- 对白手动新增复用已有 `POST /studio/shot-dialogs`（或等价路由，见 `backend/app/api/v1/routes/studio/shots.py:645`）
- 关键帧生成/应用复用 `StudioImageTasksService`、`StudioShotFrameImagesService`、`FilmService`（提示词预览/任务状态）现有接口
- `reference_mode` 手动 Select 直接使用后端已支持的 6 种枚举值，不需要新增枚举或接口参数

## 测试与验证

- `front` 下运行 `pnpm exec tsc --noEmit`
- 分镜列表：每条镜头只显示 1 个合并后的准备阶段徽标，文案随基础信息/候选状态正确切换
- "2 资产与对白确认"步骤标题、"2.1 资产关联"子标题渲染正确，`CreationGuidePage` 引导文案同步更新
- 对白确认：点击"新增对白"能插入可编辑空行，输入内容后自动创建成功，刷新页面后仍保留；未输入内容直接离开不产生脏数据
- 生成视频步骤：切换"参考模式" Select，下方关键帧卡片按选中模式动态增减
- 关键帧卡片"生成"弹窗：默认勾选当前已关联全部资产，可取消勾选/拖拽排序，提交后能生成候选图片并轮询到完成
- 候选图片点击"使用"后，对应帧类型的 `reference_frames_ready` 诊断项从"未通过"变为"通过"
- 选择只需要 `first` 的模式且已设置首帧后，"生成视频"按钮可用，能进入提示词预览与积分确认弹窗

## 文档影响

- `CLAUDE.md` 页面职责边界已同步更新（见"已完成的前置修改"）
- 实施完成后需要同步 `site/content/docs/architecture/generation-workspace.md`（关键帧面板已迁移到镜头详情页这一事实）
- `docs/superpowers/specs/2026-07-02-project-shot-flow-redesign-design.md` 的"生成模式与模型能力"目标保持不变，仍待后续独立实施；本设计不修改该文档
