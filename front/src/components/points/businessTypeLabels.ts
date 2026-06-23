/**
 * 积分业务类型 → 中文展示文案映射表。
 *
 * 后端 point_transactions.business_type 以蛇形英文键记录（如 script_divide），
 * 前端在流水列表/明细等位置需要将其渲染为用户可读的中文标签，统一在此维护映射，
 * 避免散落在多个组件内硬编码。
 */
export const BUSINESS_TYPE_LABELS: Record<string, string> = {
  script_divide: '分镜拆解',
  script_extract: '分镜提取',
  script_merge: '实体合并',
  script_consistency: '一致性检查',
  script_variant: '变体分析',
  script_character_portrait: '角色形象分析',
  script_prop_info: '道具信息分析',
  script_scene_info: '场景信息分析',
  script_costume_info: '服装信息分析',
  script_optimize: '剧本优化',
  script_simplify: '剧本精简',
  image_generation: '图片生成',
  video_generation: '视频生成',
}

/**
 * 将业务类型键格式化为中文标签。
 *
 * - 传入 null/undefined/空串返回占位符「—」，避免流水展示出现空白。
 * - 未命中映射表时回退展示原始键，便于新业务类型上线后不丢失信息。
 */
export function formatBusinessType(key: string | null | undefined): string {
  if (!key) return '—'
  return BUSINESS_TYPE_LABELS[key] ?? key
}
