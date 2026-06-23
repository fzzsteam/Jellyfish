# 积分展示样式升级设计文档

日期：2026-06-23

## 背景

前端积分相关展示（余额、单价、消耗提示）与普通字段视觉区分度不足，全部为纯文本。本次统一升级为金币感视觉风格，抽取共用组件。

## 新增组件

### `PointsBadge`

文件：`front/src/components/points/PointsBadge.tsx`

```ts
type PointsBadgeProps = {
  value: number | null | undefined
  suffix?: string        // "积分/次" "积分/张" "积分/秒" 等
  size?: 'sm' | 'md' | 'lg'  // 默认 'md'
  insufficient?: boolean // true 时切换为橙红警示色
}
```

三档视觉规格：

| size | 场景 | 图标大小 | 数字样式 | 容器样式 |
|------|------|---------|---------|---------|
| `lg` | 积分页余额、管理详情余额 | 18px | `text-2xl font-bold text-amber-500` | 金色渐变卡片 `bg-gradient-to-r from-amber-50 to-yellow-50 rounded-xl px-4 py-2` |
| `md` | 模型详情单价、管理详情字段 | 14px | `text-base font-semibold text-amber-500` | pill `bg-amber-50 rounded-full px-2 py-0.5` |
| `sm` | 表格列、生成按钮旁提示 | 12px | `text-xs font-medium text-amber-500` | 无背景，纯色文字 + 图标 |

颜色：`amber-500` 正常 / `orange-500` 不足警示 / `gray-400` null 值占位"—"

### `PointsAccountCard`

文件：`front/src/components/points/PointsAccountCard.tsx`

横排三个 stat 块，替代 `Descriptions` 三栏：
- 可用积分：`lg` PointsBadge（金色）
- 冻结积分：`md` PointsBadge（橙色，insufficient=true）
- 总余额：`md` PointsBadge（灰色中性）

```ts
type PointsAccountCardProps = {
  summary: PointsSummaryRead | null
  loading?: boolean
}
```

## 改动位置

| 文件 | 当前 | 改后 |
|------|------|------|
| `MainLayout.tsx` | 灰色文字"可用 X" | `sm` PointsBadge 金色 |
| `PointsCostHint.tsx` | 灰色/橙色纯文字 | `sm` PointsBadge，insufficient 控制警示色 |
| `PointsPage.tsx` | Descriptions 三栏 | PointsAccountCard；流水 amount 列 sm PointsBadge |
| `AdminUserDetailPage.tsx` | Descriptions 三栏 | PointsAccountCard；流水 amount 列 sm PointsBadge |
| `AdminUserListPage.tsx` | "X / Y"纯文本 | sm PointsBadge(available) + sm PointsBadge(frozen, orange) |
| `ModelsTab.tsx` | 纯文本 + suffix | 表格列 sm / 侧边详情 md PointsBadge |
