import { useEffect, useState } from 'react'
import { message, Spin } from 'antd'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { StudioShotsService } from '../../../services/generated'
import {
  getChapterShotDetailPath,
  getChapterShotsPath,
} from '../project/ProjectWorkbench/routes'

/**
 * 兼容旧章节工作室链接，将入口转发到首个镜头详情或分镜列表。
 */
const ChapterStudioRedirect = () => {
  const { projectId, chapterId } = useParams()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId || !chapterId) return

    let cancelled = false

    const redirectLegacyStudio = async () => {
      setLoading(true)
      try {
        const res = await StudioShotsService.listShotsApiV1StudioShotsGet({
          chapterId,
          page: 1,
          pageSize: 1,
          order: 'index',
          isDesc: false,
        })
        if (cancelled) return

        const firstShot = res.data?.items?.[0]
        const target = firstShot
          ? getChapterShotDetailPath(projectId, chapterId, firstShot.id, 'generate')
          : getChapterShotsPath(projectId, chapterId)
        navigate(target, { replace: true })
      } catch {
        if (cancelled) return

        message.error('无法打开旧工作室链接，已返回分镜列表')
        navigate(getChapterShotsPath(projectId, chapterId), { replace: true })
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    redirectLegacyStudio()

    return () => {
      cancelled = true
    }
  }, [chapterId, navigate, projectId])

  if (!projectId || !chapterId) {
    return <Navigate to="/projects" replace />
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 64 }}>
      {loading ? <Spin /> : null}
    </div>
  )
}

export default ChapterStudioRedirect
