# 镜头详情页「基础信息」体验优化设计

日期：2026-07-05
范围：`front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`、`ChapterShotBasicInfoSection.tsx`、后端 `ShotDetail` 相关模型/服务

## 背景

镜头详情页第一步「基础信息」存在两个体验问题，另外详情页整体的 Tab 导航在小窗口内滚动时会被卷走：

1. 「基础信息」Tab 内有两个「保存」按钮（剧本摘录旁、镜头语言默认值面板标题旁），但两者绑定的是同一个 `onSave` 回调，点击任意一个都会把标题/剧本摘录 + 景别/机位/运镜/时长/动作拍点全部一起保存。视觉上暗示"分开保存"，实际功能完全重复，容易让人误解。
2. 每条「动作拍点」上方展示的「触发/峰值/收束」三色标签，是后端 `app/services/studio/action_beats.py` 用关键词规则实时推断出来的只读展示值，不落库。该阶段结果会实际影响「关键帧生成」链路（`shot_frame_prompt_tasks.py` 的 `pick_action_beat_for_frame`）挑选首帧/尾帧/中间帧使用哪条拍点原文并注入生成提示词——但用户目前无法手动指定或修正推断结果，一旦关键词没命中导致误判，只能眼看着错的拍点被送进生成链路。
3. 详情页 4 个 Tab（1 基础信息 / 2 资产与对白确认 / 3 生成视频 / 4 视频结果）放在一个可滚动的 Card 内，向下滚动 Tab 内容时，导航条本身会被一起卷走，不方便随时切换 Tab。

## 设计

### 一、合并重复的保存按钮

- 移除 `ChapterShotBasicInfoSection.tsx` 中剧本摘录旁（现 99-107 行）、镜头语言默认值面板标题旁（现 123-125 行）两个小「保存」按钮。
- 在「基础信息」Tab 内容整体底部新增一个单一的「保存基础信息」主按钮，点击后仍调用现有 `onSave` → `saveShot()`，保存范围和现在完全一致（标题/剧本摘录 + camera_shot/angle/movement/duration/action_beats 一次性提交）。
- 组件现有的 `saving`、`semanticSaving` 两个 loading 状态本来就由 `saveShot()` 同步置位/复位，按钮合并后不再需要区分，合并为一个 `saving` 状态，`ChapterShotEditPage.tsx` 中对应精简。

### 二、动作拍点阶段支持手动指定（已撤销，不实施）

最初方案是给 `ShotDetail` 新增 `action_beat_phase_overrides` 字段持久化手动选择的阶段。实现过程中发现：
- 该字段需要新增数据库列（即使是纯新增、不影响存量数据的 `ALTER TABLE`），涉及模型/schema/迁移 SQL/多处服务调用点的改动。
- 用户在评审时明确表示不希望新增字段/改动数据库结构；在确认现有自动推断已经带有「关键词命中优先、无命中则按位置兜底（首条 trigger、总数≥3 时末条 aftermath、其余 peak）」的完整兜底逻辑、不会出现空标签后，决定维持现状，不做手动覆盖能力。

结论：本次不改动 `action_beats.py` 的推断逻辑，也不新增任何存储字段；`触发/峰值/收束` 标签继续保持只读、实时推断。

### 三、Tab 导航条吸顶悬浮

- `ChapterShotEditPage.tsx` 中 `<Tabs activeKey={editorTabKey} ... />`（约 3429 行）新增 `tabBarStyle={{ position: 'sticky', top: 0, zIndex: 10, background: '#fff' }}`。antd 5.10 的 `Tabs`（继承自 `rc-tabs`）原生支持 `tabBarStyle: React.CSSProperties`，无需自定义 `renderTabBar`。
- 外层 `Card` 的 `bodyStyle` 已经是 `overflow: 'auto'` 的滚动容器，吸顶效果相对该容器生效：滚动「基础信息/资产与对白确认/生成视频/视频结果」内容时，四个 Tab 的导航条会一直停留在卡片顶部。
- 实现细节（非独立设计决策，实现时顺手处理）：Card body 有 12px padding，吸顶后导航条与卡片顶边之间可能留一点空隙，用负外边距或调整 padding 抵消即可。

## 影响范围 / 收尾检查

- 本次不涉及后端 API 变更，无需运行 `pnpm run openapi:update`。
- 前端改动需通过 `pnpm exec tsc --noEmit`。
- 不涉及 `shot.status` / video-readiness 语义，不改动分镜工作室（`ChapterStudio.tsx`）。

## 不在本次范围内

- 动作拍点阶段手动覆盖（评审后撤销，见上）。
- 「自动推断」关键词规则本身的准确性优化。
- 关键帧生成弹窗、视频提示词预览弹窗的其余交互改动。
