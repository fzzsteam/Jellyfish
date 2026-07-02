import type { ShotRead } from '../../../services/generated'

export type ShotFlowStateKey = 'basic' | 'confirm' | 'running' | 'generatable' | 'result'
export type ShotFlowDetailTab = 'basic' | 'confirm' | 'generate' | 'results'
export type ShotFlowFilterKey = 'all' | 'basic' | 'confirm' | 'generatable' | 'result'

export type ShotRuntimeLike = {
  has_active_tasks?: boolean
  active_task_count?: number
}

export type ShotFlowState = {
  key: ShotFlowStateKey
  tab: ShotFlowDetailTab
  label: string
  buttonLabel: string
  tagColor: string
  hint: string
}

/**
 * 计算分镜列表面向用户的流程状态，统一隔离 shot.status 与运行时任务状态的语义。
 */
export function getShotFlowState(shot: ShotRead, runtime?: ShotRuntimeLike): ShotFlowState {
  const hasBasic = Boolean(shot.title?.trim()) && Boolean(shot.script_excerpt?.trim())
  const hasResult = Boolean(shot.generated_video_file_id?.trim())
  const activeTaskCount = runtime?.active_task_count ?? 1

  if (hasResult) {
    return {
      key: 'result',
      tab: 'results',
      label: '已有结果',
      buttonLabel: '查看结果',
      tagColor: 'success',
      hint: '当前镜头已有生成视频，可查看或下载结果',
    }
  }

  if (runtime?.has_active_tasks) {
    return {
      key: 'running',
      tab: 'generate',
      label: '任务运行中',
      buttonLabel: '查看生成',
      tagColor: 'processing',
      hint: `当前镜头有 ${activeTaskCount} 个运行中任务`,
    }
  }

  if (shot.status === 'ready') {
    return {
      key: 'generatable',
      tab: 'generate',
      label: '可生成',
      buttonLabel: '生成视频',
      tagColor: 'blue',
      hint: '信息提取已确认，可进入生成视频步骤',
    }
  }

  if (!hasBasic) {
    return {
      key: 'basic',
      tab: 'basic',
      label: '基础待补',
      buttonLabel: '补充信息',
      tagColor: 'gold',
      hint: '请先补齐标题和剧本摘录',
    }
  }

  return {
    key: 'confirm',
    tab: 'confirm',
    label: '待确认',
    buttonLabel: '确认提取',
    tagColor: 'warning',
    hint: shot.extraction?.state === 'not_extracted'
      ? '请先完成信息提取或标记无需提取'
      : '请先完成资产与对白候选确认',
  }
}
