import { Card, Button, Statistic, Row, Col, Progress, Spin } from 'antd'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import type { TabKey } from '../constants'
import { useProject, useChapters } from '../hooks/useProjectData'
import { StudioShotLinksService } from '../../../../../services/generated'
import {
  loadProjectFlowStatsForChapters,
  type ProjectFlowStats,
} from '../projectFlowStats'

type AssetHealthMetric = {
  total: number
  generated: number
}

type AssetHealthCounts = {
  roles: AssetHealthMetric
  scenes: AssetHealthMetric
  props: AssetHealthMetric
}

/**
 * Loads project-level asset image completion metrics for one asset kind.
 * A non-empty thumbnail means the linked asset already has at least one
 * successfully generated image available to show in the project asset library.
 */
async function loadProjectAssetHealthMetric(projectId: string, entityType: 'character' | 'scene' | 'prop'): Promise<AssetHealthMetric> {
  const pageSize = 100
  let page = 1
  let total = 0
  let generated = 0
  let maxPage = 1

  do {
    const res = await StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
      entityType,
      projectId,
      chapterId: null,
      shotId: null,
      assetId: null,
      order: null,
      isDesc: false,
      page,
      pageSize,
    })
    const data = res.data
    const items = data?.items ?? []
    total = data?.pagination.total ?? total
    maxPage = data?.pagination.max_page ?? maxPage
    generated += items.filter((item) => typeof item?.thumbnail === 'string' && item.thumbnail.trim().length > 0).length
    page += 1
  } while (page <= maxPage)

  return { total, generated }
}

/**
 * Loads project-level asset link totals and image completion counts.
 * The asset tabs use this same project-only link endpoint, so the snapshot
 * reflects the current project asset library rather than stale project stats.
 */
async function loadProjectAssetHealthCounts(projectId: string): Promise<AssetHealthCounts> {
  const [roles, scenes, props] = await Promise.all(
    (['character', 'scene', 'prop'] as const).map((entityType) => loadProjectAssetHealthMetric(projectId, entityType)),
  )
  return { roles, scenes, props }
}

export function DashboardTab(_props: { onSelectTab: (tab: TabKey) => void }) {
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const { project, loading: projectLoading } = useProject(projectId)
  const { chapters, loading: chaptersLoading } = useChapters(projectId)
  const [flowStats, setFlowStats] = useState<ProjectFlowStats>({
    totalShots: 0,
    pendingConfirmShots: 0,
    preparedShots: 0,
    readyShots: 0,
    generatingShots: 0,
    activeVideoTasks: 0,
    videoCompletedShots: 0,
  })
  const [flowStatsLoading, setFlowStatsLoading] = useState(false)
  const [assetHealthCounts, setAssetHealthCounts] = useState<AssetHealthCounts>({
    roles: { total: 0, generated: 0 },
    scenes: { total: 0, generated: 0 },
    props: { total: 0, generated: 0 },
  })
  const [assetHealthLoading, setAssetHealthLoading] = useState(false)

  const loading = projectLoading || chaptersLoading
  const chaptersByIndex = [...chapters].sort((a, b) => a.index - b.index)
  const incompleteChapters = chaptersByIndex.filter((c) => c.status !== 'done')

  useEffect(() => {
    let cancelled = false
    if (!projectId || !chapters.length) {
      setFlowStats({
        totalShots: 0,
        pendingConfirmShots: 0,
        preparedShots: 0,
        readyShots: 0,
        generatingShots: 0,
        activeVideoTasks: 0,
        videoCompletedShots: 0,
      })
      return () => {
        cancelled = true
      }
    }

    const run = async () => {
      setFlowStatsLoading(true)
      try {
        const stats = await loadProjectFlowStatsForChapters(chapters)
        if (!cancelled) setFlowStats(stats)
      } catch {
        if (!cancelled) {
          setFlowStats({
            totalShots: 0,
            pendingConfirmShots: 0,
            preparedShots: 0,
            readyShots: 0,
            generatingShots: 0,
            activeVideoTasks: 0,
            videoCompletedShots: 0,
          })
        }
      } finally {
        if (!cancelled) setFlowStatsLoading(false)
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [chapters, projectId])

  useEffect(() => {
    let cancelled = false
    if (!projectId) {
      setAssetHealthCounts({
        roles: { total: 0, generated: 0 },
        scenes: { total: 0, generated: 0 },
        props: { total: 0, generated: 0 },
      })
      return () => {
        cancelled = true
      }
    }

    const run = async () => {
      setAssetHealthLoading(true)
      try {
        const counts = await loadProjectAssetHealthCounts(projectId)
        if (!cancelled) setAssetHealthCounts(counts)
      } catch {
        if (!cancelled) {
          setAssetHealthCounts({
            roles: { total: 0, generated: 0 },
            scenes: { total: 0, generated: 0 },
            props: { total: 0, generated: 0 },
          })
        }
      } finally {
        if (!cancelled) setAssetHealthLoading(false)
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [projectId])

  if (loading && !project) {
    return (
      <div className="flex justify-center items-center py-16">
        <Spin size="large" tip="加载中…" />
      </div>
    )
  }
  if (!project) {
    return null
  }

  const incompleteCount = incompleteChapters.length
  const assetHealthPercent = (metric: AssetHealthMetric) =>
    metric.total > 0 ? Math.round((metric.generated / metric.total) * 100) : 0

  return (
    <div className="space-y-6">
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small" className="h-full">
            <Statistic title="未完成章节" value={incompleteCount} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small" className="h-full">
            <Statistic
              title="待确认分镜"
              value={flowStats.pendingConfirmShots}
              suffix={flowStats.totalShots ? `/ ${flowStats.totalShots}` : undefined}
              loading={flowStatsLoading}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small" className="h-full">
            <Statistic
              title="准备完成分镜"
              value={flowStats.readyShots}
              loading={flowStatsLoading}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small" className="h-full">
            <Statistic
              title="生成中分镜"
              value={flowStats.generatingShots}
              loading={flowStatsLoading}
              prefix={<ClockCircleOutlined />}
            />
            <Progress
              percent={flowStats.totalShots ? Math.round((flowStats.readyShots / flowStats.totalShots) * 100) : project.progress}
              showInfo={false}
              size="small"
              strokeColor={{ from: '#6366f1', to: '#a855f7' }}
              className="mt-1"
            />
          </Card>
        </Col>
      </Row>

      <Card title="资产健康快照" size="small">
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>角色</span>
            <span className="text-gray-500">{assetHealthLoading ? '...' : `${assetHealthCounts.roles.total} 项`}</span>
          </div>
          <Progress percent={assetHealthPercent(assetHealthCounts.roles)} size="small" showInfo={false} />
          <div className="flex justify-between text-sm">
            <span>场景</span>
            <span className="text-gray-500">{assetHealthLoading ? '...' : `${assetHealthCounts.scenes.total} 项`}</span>
          </div>
          <Progress percent={assetHealthPercent(assetHealthCounts.scenes)} size="small" showInfo={false} />
          <div className="flex justify-between text-sm">
            <span>道具</span>
            <span className="text-gray-500">{assetHealthLoading ? '...' : `${assetHealthCounts.props.total} 项`}</span>
          </div>
          <Progress percent={assetHealthPercent(assetHealthCounts.props)} size="small" showInfo={false} />
        </div>
        <Button type="link" className="p-0 mt-2" onClick={() => navigate('/assets')}>
          管理资产
        </Button>
      </Card>
    </div>
  )
}
