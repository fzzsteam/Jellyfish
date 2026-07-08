import type { TaskStatus } from '../../services/generated'

/** 仍在推进中的任务状态集合，供任务中心和左侧菜单统一判断。 */
export const ACTIVE_TASK_STATUSES: TaskStatus[] = ['pending', 'running', 'streaming']

/** 任务中心状态筛选平铺选项。 */
export const TASK_STATUS_FILTER_OPTIONS: Array<{ label: string; value: TaskStatus | 'all' | 'active' }> = [
  { label: '全部', value: 'all' },
  { label: '进行中', value: 'active' },
  { label: '已完成', value: 'succeeded' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
]
