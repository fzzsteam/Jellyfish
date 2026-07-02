export function getProjectChaptersPath(projectId: string) {
  return `/projects/${projectId}/chapters`
}

export function getChapterStudioPath(projectId: string, chapterId: string) {
  return `/projects/${projectId}/chapters/${chapterId}/studio`
}

export function getChapterShotsPath(projectId: string, chapterId: string) {
  return `/projects/${projectId}/chapters/${chapterId}/shots`
}

export function getChapterShotEditPath(projectId: string, chapterId: string, shotId: string) {
  return `/projects/${projectId}/chapters/${chapterId}/shots/${shotId}/edit`
}

export type ShotDetailTabKey = 'basic' | 'confirm' | 'generate' | 'results'

/**
 * 生成分镜详情页地址，用于在不同业务入口间稳定跳转到指定详情标签。
 */
export function getChapterShotDetailPath(
  projectId: string,
  chapterId: string,
  shotId: string,
  tab?: ShotDetailTabKey,
) {
  const base = getChapterShotEditPath(projectId, chapterId, shotId)
  return tab ? `${base}?tab=${tab}` : base
}

export function getProjectEditorPath(projectId: string) {
  return `/projects/${projectId}/editor`
}
