import { useState, useEffect, useMemo, useRef } from 'react'
import { Card, Button, Tag, Space, Table, Empty, Modal, Input, Dropdown, message } from 'antd'
import type { MenuProps, TableColumnsType } from 'antd'
import {
  EditOutlined,
  LoadingOutlined,
  MoreOutlined,
  PlusOutlined,
  StopOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { StudioChaptersService, StudioShotLinksService } from '../../../../../services/generated'
import { chapterStatusMap } from '../constants'
import { getChapterShotsPath } from '../routes'
import { useChapters, newId, type Chapter } from '../hooks/useProjectData'
import { ChapterRawTextEditorModal } from '../../../chapter/components/ChapterRawTextEditorModal'
import { getChapterPreparationState } from '../chapterPreparation'
import { loadChapterFlowStats, type ChapterFlowStats, type ProjectFlowStats } from '../projectFlowStats'
import { executeTaskCancel } from '../../../components/taskActionHelpers'
import { TASK_COPY } from '../../../components/taskCopy'
import { useTaskPageContext } from '../../../components/taskPageContext'
import { useTaskUiStore } from '../../../components/taskUiStore'
import {
  createRelationTaskState,
  upsertRelationTaskStateInMap,
  useChapterDivisionTaskMapPolling,
} from '../chapterDivisionTasks'

const { TextArea } = Input
const CREATE_PARAM = 'create'
const EDIT_PARAM = 'edit'

const emptyProjectFlowStats: ProjectFlowStats = {
  totalShots: 0,
  pendingConfirmShots: 0,
  preparedShots: 0,
  readyShots: 0,
  generatingShots: 0,
  activeVideoTasks: 0,
  videoCompletedShots: 0,
}

type AssetHealthMetric = {
  total: number
  generated: number
}

type AssetHealthCounts = {
  roles: AssetHealthMetric
  scenes: AssetHealthMetric
  props: AssetHealthMetric
}

const emptyAssetHealthCounts: AssetHealthCounts = {
  roles: { total: 0, generated: 0 },
  scenes: { total: 0, generated: 0 },
  props: { total: 0, generated: 0 },
}

/**
 * 汇总每章分镜流转数据，避免章节表格和顶部总览分别请求同一批接口。
 * 返回结构与项目总览统计一致，方便后续继续复用展示口径。
 */
function sumChapterFlowStats(rows: ChapterFlowStats[]): ProjectFlowStats {
  return rows.reduce<ProjectFlowStats>(
    (acc, item) => ({
      totalShots: acc.totalShots + item.totalShots,
      pendingConfirmShots: acc.pendingConfirmShots + item.pendingConfirmShots,
      preparedShots: acc.preparedShots + item.preparedShots,
      readyShots: acc.readyShots + item.readyShots,
      generatingShots: acc.generatingShots + item.generatingShots,
      activeVideoTasks: acc.activeVideoTasks + item.activeVideoTasks,
      videoCompletedShots: acc.videoCompletedShots + item.videoCompletedShots,
    }),
    emptyProjectFlowStats,
  )
}

/**
 * 读取单类项目资产的图片完成度，用于章节列表顶部的资产健康快照。
 * 这里直接复用资产 Tab 的项目级关联接口，避免引入额外手写 service。
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
 * 并发汇总角色、场景、道具三类资产健康数据。
 * 章节列表只展示轻量快照，详细管理仍跳转到资产管理页处理。
 */
async function loadProjectAssetHealthCounts(projectId: string): Promise<AssetHealthCounts> {
  const [roles, scenes, props] = await Promise.all(
    (['character', 'scene', 'prop'] as const).map((entityType) => loadProjectAssetHealthMetric(projectId, entityType)),
  )
  return { roles, scenes, props }
}

/**
 * 章节列表标题行内的轻量摘要，承接项目工作台原有关键统计。
 * 它只展示关键数字，避免用独立顶部区域抢占章节表格的主视觉。
 */
function ChapterTopSummary({
  incompleteCount,
  flowStats,
  flowLoading,
  assetCounts,
  assetLoading,
  onManageAssets,
}: {
  incompleteCount: number
  flowStats: ProjectFlowStats
  flowLoading: boolean
  assetCounts: AssetHealthCounts
  assetLoading: boolean
  onManageAssets: () => void
}) {
  const chapterItems = [
    flowLoading ? '未完成 ...' : `未完成 ${incompleteCount}`,
    flowLoading ? '待确认 ...' : `待确认 ${flowStats.pendingConfirmShots}/${flowStats.totalShots}`,
    flowLoading ? '准备完成 ...' : `准备完成 ${flowStats.readyShots}`,
  ]
  const assetItems = [
    { label: '角色', metric: assetCounts.roles },
    { label: '场景', metric: assetCounts.scenes },
    { label: '道具', metric: assetCounts.props },
  ]

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs">
      <div className="inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1 rounded border border-gray-200 bg-white px-2.5 py-1 shadow-sm shadow-gray-100/50">
        <span className="inline-flex items-center gap-1 font-medium text-gray-700">
          <span className="h-3 w-0.5 rounded bg-blue-500" />
          章节
        </span>
        {chapterItems.map((item) => (
          <span key={item} className="text-gray-500">
            {item}
          </span>
        ))}
      </div>
      <div className="inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1 rounded border border-gray-200 bg-white px-2.5 py-1 shadow-sm shadow-gray-100/50">
        <span className="inline-flex items-center gap-1 font-medium text-gray-700">
          <span className="h-3 w-0.5 rounded bg-emerald-500" />
          资产
        </span>
        {assetItems.map((item) => (
          <span key={item.label} className="text-gray-500">
            {assetLoading ? `${item.label} ...` : `${item.label} ${item.metric.generated}/${item.metric.total}`}
          </span>
        ))}
        <Button type="link" size="small" className="h-auto p-0 text-xs leading-none" onClick={onManageAssets}>
          管理
        </Button>
      </div>
    </div>
  )
}

export function ChaptersTab() {
  const taskCopy = TASK_COPY.chapterDivision
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const { chapters, loading, refresh, patchChapterLocal } = useChapters(projectId)

  const [editOpen, setEditOpen] = useState(false)
  const [editingChapter, setEditingChapter] = useState<Chapter | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [createTitle, setCreateTitle] = useState('')
  const [createContent, setCreateContent] = useState('')
  const [chapterFlowMap, setChapterFlowMap] = useState<Record<string, ChapterFlowStats>>({})
  const [projectFlowStats, setProjectFlowStats] = useState<ProjectFlowStats>(emptyProjectFlowStats)
  const [projectFlowStatsLoading, setProjectFlowStatsLoading] = useState(false)
  const [assetHealthCounts, setAssetHealthCounts] = useState<AssetHealthCounts>(emptyAssetHealthCounts)
  const [assetHealthLoading, setAssetHealthLoading] = useState(false)
  const [chapterDivisionActionId, setChapterDivisionActionId] = useState<string | null>(null)
  const taskUiUpsert = useTaskUiStore((state) => state.upsertTask)
  const taskUiRemove = useTaskUiStore((state) => state.removeTask)
  const syncedTaskIdsRef = useRef<string[]>([])
  const chapterIds = useMemo(() => chapters.map((chapter) => chapter.id), [chapters])
  useTaskPageContext(
    chapterIds.map((id) => ({
      relationType: 'chapter_division',
      relationEntityId: id,
    })),
  )
  const { taskMap: chapterDivisionTaskMap, setTrackedTaskMap: setChapterDivisionTaskMap } = useChapterDivisionTaskMapPolling({
    chapterIds,
    onTasksSettled: async () => {
      await refresh()
    },
  })

  const createParam = searchParams.get(CREATE_PARAM)
  const editParam = searchParams.get(EDIT_PARAM)
  useEffect(() => {
    if (createParam === '1') {
      setCreateOpen(true)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.delete(CREATE_PARAM)
          return next
        },
        { replace: true }
      )
    }
  }, [createParam, setSearchParams])

  useEffect(() => {
    if (!editParam) return
    const target = chapters.find((chapter) => chapter.id === editParam)
    if (!target) return
    openEditModal(target)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.delete(EDIT_PARAM)
        return next
      },
      { replace: true }
    )
  }, [chapters, editParam, setSearchParams])

  useEffect(() => {
    let cancelled = false
    if (!chapters.length) {
      setChapterFlowMap({})
      setProjectFlowStats(emptyProjectFlowStats)
      return () => {
        cancelled = true
      }
    }

    const run = async () => {
      setProjectFlowStatsLoading(true)
      try {
        const rows = await loadChapterFlowStats(chapters)
        if (!cancelled) {
          setChapterFlowMap(Object.fromEntries(rows.map((row) => [row.chapterId, row])))
          setProjectFlowStats(sumChapterFlowStats(rows))
        }
      } catch {
        if (!cancelled) {
          setChapterFlowMap({})
          setProjectFlowStats(emptyProjectFlowStats)
        }
      } finally {
        if (!cancelled) setProjectFlowStatsLoading(false)
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [chapters])

  const incompleteChapterCount = useMemo(
    () => chapters.filter((chapter) => chapter.status !== 'done').length,
    [chapters],
  )

  useEffect(() => {
    let cancelled = false
    if (!projectId) {
      setAssetHealthCounts(emptyAssetHealthCounts)
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
        if (!cancelled) setAssetHealthCounts(emptyAssetHealthCounts)
      } finally {
        if (!cancelled) setAssetHealthLoading(false)
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [projectId])

  const openEditModal = (chapter: Chapter) => {
    setEditingChapter(chapter)
    setEditOpen(true)
  }

  const openCreateNextStep = (chapter: Chapter, hasRawText: boolean) => {
    if (!projectId) return
    Modal.confirm({
      title: '章节创建成功',
      content: hasRawText
        ? '这一章已经有原文内容，接下来更适合进入分镜列表发起提取，并继续处理镜头队列。'
        : '这一章还没有原文内容，建议先补章节原文。',
      okText: hasRawText ? '进入分镜列表' : '继续编辑原文',
      cancelText: '稍后处理',
      onOk: () => {
        if (hasRawText) {
          navigate(getChapterShotsPath(projectId, chapter.id))
          return
        }
        openEditModal(chapter)
      },
    })
  }

  const handleCreateChapter = async () => {
    if (!createTitle.trim()) {
      message.warning('请输入章节标题')
      return
    }
    if (!projectId) return
    try {
      const nextIndex = Math.max(0, ...chapters.map((c) => c.index)) + 1
      const createdId = newId('c')
      const title = createTitle.trim()
      const rawText = createContent
      const draftChapter: Chapter = {
        id: createdId,
        projectId,
        index: nextIndex,
        title,
        summary: '',
        rawText,
        storyboardCount: 0,
        status: 'draft',
        updatedAt: new Date().toISOString(),
      }
      await StudioChaptersService.createChapterApiV1StudioChaptersPost({
        requestBody: {
          id: createdId,
          project_id: projectId,
          index: nextIndex,
          title,
          summary: '',
          raw_text: rawText || undefined,
          storyboard_count: 0,
          status: 'draft',
        },
      })
      message.success('章节创建成功')
      setCreateOpen(false)
      setCreateTitle('')
      setCreateContent('')
      await refresh()
      openCreateNextStep(draftChapter, !!rawText.trim())
    } catch {
      message.error('创建章节失败')
    }
  }

  const useMock = import.meta.env.VITE_USE_MOCK === 'true'
  const handleCreateChapterMock = () => {
    if (!createTitle.trim()) {
      message.warning('请输入章节标题')
      return
    }
    if (!projectId) return
    const nextIndex = Math.max(0, ...chapters.map((c) => c.index)) + 1
    const createdId = newId('c')
    const title = createTitle.trim()
    const rawText = createContent
    const draftChapter: Chapter = {
      id: createdId,
      projectId,
      index: nextIndex,
      title,
      summary: '',
      rawText,
      storyboardCount: 0,
      status: 'draft',
      updatedAt: new Date().toISOString(),
    }
    message.success('创建成功（Mock）')
    setCreateOpen(false)
    setCreateTitle('')
    setCreateContent('')
    window.setTimeout(() => openCreateNextStep(draftChapter, !!rawText.trim()), 0)
    void refresh()
  }

  const handlePrimaryAction = (record: Chapter) => {
    if (!projectId) return
    const activeTask = chapterDivisionTaskMap[record.id]
    if (activeTask) {
      navigate(getChapterShotsPath(projectId, record.id))
      return
    }
    const state = getChapterPreparationState(record)
    if (state.key === 'edit_raw') {
      navigate(getChapterShotsPath(projectId, record.id))
      return
    }
    navigate(getChapterShotsPath(projectId, record.id))
  }

  const handleCancelDivideTask = async (record: Chapter) => {
    const activeTask = chapterDivisionTaskMap[record.id]
    if (!activeTask) return
    setChapterDivisionActionId(record.id)
    try {
      await executeTaskCancel({
        taskId: activeTask.taskId,
        reason: '用户在章节页取消分镜提取',
        applyCancelData: (data) => {
          if (!data?.task_id || !data?.status) return null
          const tracked = createRelationTaskState(
            {
              task_id: data.task_id,
              status: data.status,
            },
            { cancelRequested: data.cancel_requested ?? false },
          )
          setChapterDivisionTaskMap(upsertRelationTaskStateInMap(chapterDivisionTaskMap, record.id, tracked))
          return tracked
        },
        cancelledImmediatelyMessage: taskCopy.cancelledImmediatelyMessage,
        cancelRequestedMessage: taskCopy.cancelRequestedMessage,
        fallbackErrorMessage: '取消任务失败',
      })
    } catch {
      // executeTaskCancel 已统一处理错误提示
    } finally {
      setChapterDivisionActionId(null)
    }
  }

  useEffect(() => {
    const nextTaskIds: string[] = []

    chapters.forEach((chapter) => {
      const task = chapterDivisionTaskMap[chapter.id]
      if (!task) return
      nextTaskIds.push(task.taskId)
      taskUiUpsert({
        taskId: task.taskId,
        title: taskCopy.title,
        sourceLabel: chapter.title ? `章节：${chapter.title}` : '项目工作台章节列表',
        status: task.status,
        progress: task.progress,
        cancelRequested: task.cancelRequested,
        startedAtTs: task.startedAtTs,
        finishedAtTs: task.finishedAtTs,
        elapsedMs: task.elapsedMs,
        onCancel: () => void handleCancelDivideTask(chapter),
        onNavigate: projectId ? () => navigate(getChapterShotsPath(projectId, chapter.id)) : null,
      })
    })

    syncedTaskIdsRef.current
      .filter((taskId) => !nextTaskIds.includes(taskId))
      .forEach((taskId) => taskUiRemove(taskId))

    syncedTaskIdsRef.current = nextTaskIds
  }, [chapterDivisionTaskMap, chapters, handleCancelDivideTask, navigate, projectId, taskCopy.title, taskUiRemove, taskUiUpsert])

  useEffect(() => {
    return () => {
      syncedTaskIdsRef.current.forEach((taskId) => taskUiRemove(taskId))
      syncedTaskIdsRef.current = []
    }
  }, [taskUiRemove])

  const buildActionMenuItems = (record: Chapter): MenuProps['items'] => {
    if (!projectId) return []
    const activeTask = chapterDivisionTaskMap[record.id]
    return [
      {
        key: 'shots',
        label: '进入分镜',
        onClick: () => navigate(getChapterShotsPath(projectId, record.id)),
      },
      {
        key: 'raw',
        label: '编辑原文',
        icon: <EditOutlined />,
        onClick: () => openEditModal(record),
      },
      activeTask
        ? {
            key: 'cancel_divide',
            label: activeTask.cancelRequested ? '取消请求已发出' : '取消分镜提取',
            icon: <StopOutlined />,
            disabled: activeTask.cancelRequested || chapterDivisionActionId === record.id,
            onClick: () => void handleCancelDivideTask(record),
          }
        : null,
    ].filter(Boolean)
  }

  const columns: TableColumnsType<Chapter> = [
    { title: '章节', dataIndex: 'index', key: 'index', width: 80, render: (v: number) => `第${v}集` },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, record) => (
        <Button
          type="link"
          size="small"
          style={{ paddingInline: 0 }}
          onClick={() => openEditModal(record)}
        >
          {title || '未命名章节'}
        </Button>
      ),
    },
    { title: '分镜数', dataIndex: 'storyboardCount', key: 'storyboardCount', width: 90 },
    {
      title: '准备状态',
      key: 'preparation',
      width: 180,
      render: (_, record) => {
        const activeTask = chapterDivisionTaskMap[record.id]
        if (activeTask) {
          return (
            <div className="space-y-1">
              <Tag color={activeTask.cancelRequested ? 'orange' : 'processing'}>
                {activeTask.cancelRequested ? '正在取消提取' : '分镜提取中'}
              </Tag>
              <div className="text-[11px] text-gray-500 leading-5">
                {activeTask.cancelRequested ? '已请求取消，将在当前步骤结束后停止' : '系统正在异步提取当前章节分镜'}
              </div>
            </div>
          )
        }
        const state = getChapterPreparationState(record)
        return (
          <div className="space-y-1">
            <Tag color={state.color}>{state.text}</Tag>
            {state.hint ? <div className="text-[11px] text-gray-500 leading-5">{state.hint}</div> : null}
          </div>
        )
      },
    },
    {
      title: '分镜流转',
      key: 'shotFlow',
      width: 220,
      render: (_, record) => {
        const stats = chapterFlowMap[record.id]
        return (
          <div className="flex flex-wrap gap-1">
            <Tag bordered={false} color="gold" className="mr-0">
              待确认 {stats?.pendingConfirmShots ?? 0}
            </Tag>
            <Tag bordered={false} color="green" className="mr-0">
              已就绪 {stats?.readyShots ?? 0}
            </Tag>
            <Tag bordered={false} color="processing" className="mr-0">
              生成中 {stats?.generatingShots ?? 0}
            </Tag>
          </div>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: Chapter['status']) => (
        <Tag color={chapterStatusMap[status].color}>{chapterStatusMap[status].text}</Tag>
      ),
    },
    { title: '更新时间', dataIndex: 'updatedAt', key: 'updatedAt', width: 160 },
    {
      title: '操作',
      key: 'action',
      width: 280,
      render: (_, record) => {
        const state = getChapterPreparationState(record)
        const activeTask = chapterDivisionTaskMap[record.id]
        const primaryIcon = activeTask
          ? activeTask.cancelRequested
            ? <SyncOutlined spin />
            : <LoadingOutlined />
          : state.primaryIcon
        const primaryText = activeTask
          ? activeTask.cancelRequested
            ? '查看取消进度'
            : '查看提取进度'
          : '进入分镜'

        return (
          <Space size={8} direction="vertical" className="items-start">
            <Space size={8}>
              <Button
                size="small"
                onClick={() => openEditModal(record)}
                icon={<EditOutlined />}
              >
                编辑原文
              </Button>
              <Button
                type="primary"
                size="small"
                onClick={() => handlePrimaryAction(record)}
                style={{ minWidth: 132, justifyContent: 'center' }}
                icon={primaryIcon}
              >
                {primaryText}
              </Button>
              <Dropdown
                trigger={['click']}
                menu={{ items: buildActionMenuItems(record) }}
              >
                <Button
                  size="small"
                  icon={<MoreOutlined />}
                  aria-label="更多操作"
                  loading={chapterDivisionActionId === record.id && !!activeTask}
                />
              </Dropdown>
            </Space>
          </Space>
        )
      },
    },
  ]

  if (chapters.length === 0 && !loading) {
    return (
      <>
        <Card
          title={
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>章节列表</span>
              <ChapterTopSummary
                incompleteCount={incompleteChapterCount}
                flowStats={projectFlowStats}
                flowLoading={projectFlowStatsLoading}
                assetCounts={assetHealthCounts}
                assetLoading={assetHealthLoading}
                onManageAssets={() => navigate('/assets')}
              />
            </div>
          }
          bodyStyle={{ paddingTop: 12 }}
          extra={
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建章节
            </Button>
          }
        >
          <Empty description="还没有任何章节，立即创建第一章吧" image={Empty.PRESENTED_IMAGE_SIMPLE}>
          <Space>
            <Button type="primary" size="large" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              创建第一章
            </Button>
          </Space>
        </Empty>
        </Card>
        <Modal
          title="新建章节"
          open={createOpen}
          onCancel={() => setCreateOpen(false)}
          onOk={useMock ? handleCreateChapterMock : handleCreateChapter}
          okText="创建"
          width={560}
        >
          <div className="space-y-3">
            <div>
              <span className="text-gray-600 text-sm">章节标题</span>
              <Input
                placeholder="例如：第1集 出租屋里的争吵"
                value={createTitle}
                onChange={(e) => setCreateTitle(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <span className="text-gray-600 text-sm">章节内容（可粘贴剧本）</span>
              <TextArea
                rows={6}
                placeholder="粘贴文学剧本..."
                value={createContent}
                onChange={(e) => setCreateContent(e.target.value)}
                className="mt-1 font-mono text-sm"
              />
            </div>
          </div>
        </Modal>
      </>
    )
  }

  return (
    <>
      <Card
        title={
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>章节列表</span>
            <ChapterTopSummary
              incompleteCount={incompleteChapterCount}
              flowStats={projectFlowStats}
              flowLoading={projectFlowStatsLoading}
              assetCounts={assetHealthCounts}
              assetLoading={assetHealthLoading}
              onManageAssets={() => navigate('/assets')}
            />
          </div>
        }
        bodyStyle={{ paddingTop: 12 }}
        extra={
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建章节
            </Button>
          </Space>
        }
      >
        <Table<Chapter>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={chapters}
          pagination={{ pageSize: 10 }}
          size="small"
        />

        <ChapterRawTextEditorModal
          open={editOpen}
          onClose={() => {
            setEditOpen(false)
            setEditingChapter(null)
          }}
          chapterId={editingChapter?.id}
          onSaved={(next) => {
            if (editingChapter?.id && typeof next.rawText === 'string') {
              patchChapterLocal(editingChapter.id, { rawText: next.rawText })
            }
            void refresh()
          }}
        />

        <Modal
          title="新建章节"
          open={createOpen}
          onCancel={() => setCreateOpen(false)}
          onOk={useMock ? handleCreateChapterMock : handleCreateChapter}
          okText="创建"
          width={560}
        >
          <div className="space-y-3">
            <div>
              <span className="text-gray-600 text-sm">章节标题</span>
              <Input
                placeholder="例如：第1集 出租屋里的争吵"
                value={createTitle}
                onChange={(e) => setCreateTitle(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <span className="text-gray-600 text-sm">章节内容（可粘贴剧本）</span>
              <TextArea
                rows={6}
                placeholder="粘贴文学剧本..."
                value={createContent}
                onChange={(e) => setCreateContent(e.target.value)}
                className="mt-1 font-mono text-sm"
              />
            </div>
          </div>
        </Modal>
      </Card>
    </>
  )
}
