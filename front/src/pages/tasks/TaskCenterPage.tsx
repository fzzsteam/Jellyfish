import { Button, Card, Collapse, Empty, Progress, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { CopyOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FilmService } from '../../services/generated'
import type { TaskListItemRead, TaskStatus } from '../../services/generated'
import type { TaskUiItem } from '../aiStudio/components/taskUiStore'
import { useResolvedTaskCenterTasks } from '../aiStudio/components/taskCenterMeta'
import { resolveTaskSourceLabel, resolveTaskTitle } from '../aiStudio/components/taskCopy'

const ACTIVE_STATUSES: TaskStatus[] = ['pending', 'running', 'streaming']
/** 任务中心轮询间隔，保证停留在页面时任务状态持续更新。 */
const TASK_CENTER_POLL_INTERVAL_MS = 5000

/**
 * 格式化任务时间戳，统一任务中心内的时间展示口径。
 */
function formatDateTime(ts?: number | null): string {
  if (!ts) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(ts * 1000))
}

/**
 * 为任务状态补充 UI 展示信息，确保状态标签与解释文案一致。
 */
function getStatusMeta(task: TaskListItemRead): { color: string; label: string; detail: string } {
  if (task.status === 'cancelled') {
    return { color: 'orange', label: '已取消', detail: '任务已取消。' }
  }
  if (task.cancel_requested) {
    return { color: 'orange', label: '取消中', detail: '已发送取消请求，等待任务在当前步骤结束后停止。' }
  }
  if (task.status === 'failed') {
    return { color: 'red', label: '失败', detail: '任务执行失败。' }
  }
  if (task.status === 'succeeded') {
    return { color: 'green', label: '已完成', detail: '任务已完成。' }
  }
  if (task.status === 'streaming') {
    return { color: 'cyan', label: '处理中', detail: '任务正在处理中。' }
  }
  if (task.status === 'running') {
    return { color: 'blue', label: '运行中', detail: '任务正在运行。' }
  }
  return { color: 'default', label: '等待中', detail: '任务已进入队列，等待执行。' }
}

/**
 * 组装任务中心列表里的上下文文案，尽量说明任务正在给哪个对象执行什么动作。
 */
function buildTaskSentence(task: TaskUiItem): string {
  const title = task.title?.trim() || '后台任务'
  const sourceLabel = task.sourceLabel?.trim()
  const actionPrefix =
    task.status === 'succeeded'
      ? '已为'
      : task.status === 'failed'
        ? '曾为'
        : task.status === 'cancelled'
          ? '已取消为'
          : task.cancelRequested
            ? '正在取消为'
            : '正在为'
  if (sourceLabel) {
    return `${actionPrefix} ${sourceLabel} 执行${title}`
  }
  if (task.relationType || task.relationEntityId) {
    return `${actionPrefix} ${resolveTaskSourceLabel(task.relationType, task.relationEntityId) || '关联对象'} 执行${title}`
  }
  if (task.status === 'succeeded') return `已执行${title}`
  if (task.status === 'failed') return `执行${title}时失败`
  if (task.status === 'cancelled') return `已取消${title}`
  return `正在执行${title}`
}

/**
 * 顶层任务中心页面，统一展示当前用户可见的异步任务状态与错误信息。
 */
export default function TaskCenterPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<TaskListItemRead[]>([])
  const [statusFilter, setStatusFilter] = useState<TaskStatus[]>([])
  const [taskKindFilter, setTaskKindFilter] = useState<string | undefined>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  const taskUiItems = useMemo<TaskUiItem[]>(
    () =>
      items.map((item) => ({
        taskId: item.task_id,
        title: resolveTaskTitle(item.task_kind),
        sourceLabel: resolveTaskSourceLabel(item.relation_type, item.relation_entity_id),
        status: item.status,
        progress: item.progress,
        error: item.error ?? '',
        errorTrace: item.error_trace ?? null,
        cancelRequested: item.cancel_requested ?? false,
        createdAtTs: item.created_at_ts ?? null,
        updatedAtTs: item.updated_at_ts ?? null,
        startedAtTs: item.started_at_ts ?? null,
        finishedAtTs: item.finished_at_ts ?? null,
        elapsedMs: item.elapsed_ms ?? null,
        executorType: item.executor_type ?? null,
        executorTaskId: item.executor_task_id ?? null,
        relationType: item.relation_type ?? null,
        relationEntityId: item.relation_entity_id ?? null,
        resourceType: item.resource_type ?? null,
        navigateRelationType: item.navigate_relation_type ?? null,
        navigateRelationEntityId: item.navigate_relation_entity_id ?? null,
      })),
    [items],
  )
  const resolvedTasks = useResolvedTaskCenterTasks(taskUiItems, navigate)
  const taskById = useMemo(
    () => Object.fromEntries(resolvedTasks.map((item) => [item.taskId, item])),
    [resolvedTasks],
  )

  const loadTasks = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setLoading(true)
    }
    try {
      const response = await FilmService.listTasksApiV1FilmTasksGet({
        statuses: statusFilter.length > 0 ? statusFilter : undefined,
        taskKind: taskKindFilter,
        recentSeconds: undefined,
        page,
        pageSize,
      })
      setItems(response.data?.items ?? [])
      setTotal(response.data?.pagination?.total ?? 0)
    } catch {
      if (!options?.silent) {
        message.error('加载任务中心失败')
      }
    } finally {
      if (!options?.silent) {
        setLoading(false)
      }
    }
  }, [page, pageSize, statusFilter, taskKindFilter])

  useEffect(() => {
    void loadTasks()
  }, [loadTasks])

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadTasks({ silent: true })
    }, TASK_CENTER_POLL_INTERVAL_MS)
    return () => {
      window.clearInterval(timer)
    }
  }, [loadTasks])

  const taskKindOptions = useMemo(
    () =>
      Array.from(new Set(items.map((item) => item.task_kind)))
        .filter((value) => !!value)
        .map((value) => ({ label: resolveTaskTitle(value), value })),
    [items],
  )

  const columns = useMemo<ColumnsType<TaskListItemRead>>(
    () => [
      {
        title: '任务',
        dataIndex: 'task_kind',
        width: 360,
        render: (_value, record) => {
          const task = taskById[record.task_id]
          return (
            <div className="space-y-1">
              <div className="font-medium text-sm">{task?.title || resolveTaskTitle(record.task_kind)}</div>
              <div className="text-xs text-gray-500 whitespace-pre-wrap break-words">
                {task ? buildTaskSentence(task) : resolveTaskSourceLabel(record.relation_type, record.relation_entity_id) || '无关联上下文'}
              </div>
              <Typography.Text copyable className="text-xs text-gray-400">
                {record.task_id}
              </Typography.Text>
            </div>
          )
        },
      },
      {
        title: '状态信息',
        dataIndex: 'status',
        width: 240,
        render: (_value, record) => {
          const meta = getStatusMeta(record)
          const isActive = ACTIVE_STATUSES.includes(record.status)
          return (
            <div className="space-y-2">
              <Tag color={meta.color}>
                <span className="inline-flex items-center gap-1.5">
                  {isActive ? (
                    <span className="relative inline-flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-50" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
                    </span>
                  ) : null}
                  {meta.label}
                </span>
              </Tag>
              <Progress
                percent={Math.max(0, Math.min(100, Math.round(record.progress)))}
                size="small"
                showInfo={false}
                status={isActive ? 'active' : undefined}
              />
              <div className="text-xs text-gray-500 whitespace-pre-wrap break-words">{meta.detail}</div>
            </div>
          )
        },
      },
      {
        title: '时间',
        width: 240,
        render: (_value, record) => (
          <div className="text-xs text-gray-500 space-y-1">
            <div>开始：{formatDateTime(record.started_at_ts)}</div>
            <div>结束：{formatDateTime(record.finished_at_ts)}</div>
          </div>
        ),
      },
      {
        title: '错误',
        dataIndex: 'error',
        width: 320,
        render: (_value, record) => {
          const error = (record.error || '').trim()
          const errorTrace = (record.error_trace || '').trim()
          if (!error && !errorTrace) {
            return <span className="text-gray-400">-</span>
          }
          return (
            <div className="max-w-[300px] space-y-2">
              {error ? (
                <pre className="max-h-[120px] overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-700">
                  {error}
                </pre>
              ) : null}
              {errorTrace ? (
                <Collapse
                  ghost
                  size="small"
                  items={[
                    {
                      key: 'error-trace',
                      label: '查看错误详情',
                      children: (
                        <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap rounded bg-gray-950 p-3 text-xs text-gray-100">
                          {errorTrace}
                        </pre>
                      ),
                    },
                  ]}
                />
              ) : null}
            </div>
          )
        },
      },
      {
        title: '操作',
        width: 120,
        render: (_value, record) => (
          <Space direction="vertical" size={8}>
            <Button
              size="small"
              icon={<CopyOutlined />}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(record.task_id)
                  message.success('任务 ID 已复制')
                } catch {
                  message.error('复制任务 ID 失败')
                }
              }}
            >
              复制 ID
            </Button>
            {ACTIVE_STATUSES.includes(record.status) ? (
              <Button
                size="small"
                danger
                icon={<StopOutlined />}
                disabled={record.cancel_requested}
                onClick={async () => {
                  try {
                    await FilmService.cancelTaskApiV1FilmTasksTaskIdCancelPost({
                      taskId: record.task_id,
                      requestBody: { reason: '用户在任务中心取消任务' },
                    })
                    message.success(record.cancel_requested ? '任务正在取消' : '已发送取消请求')
                    void loadTasks()
                  } catch {
                    message.error('取消任务失败')
                  }
                }}
              >
                {record.cancel_requested ? '取消中' : '取消'}
              </Button>
            ) : null}
          </Space>
        ),
      },
    ],
    [loadTasks, taskById],
  )

  return (
    <div className="h-full overflow-auto bg-neutral-100 p-4">
      <Card
        title="任务中心"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void loadTasks()}>
            刷新
          </Button>
        }
      >
        <div className="mb-4 flex flex-wrap gap-3">
          <Select
            mode="multiple"
            allowClear
            placeholder="按状态筛选"
            style={{ minWidth: 260 }}
            value={statusFilter}
            onChange={(value) => {
              setStatusFilter(value)
              setPage(1)
            }}
            options={[
              { label: '等待中', value: 'pending' },
              { label: '运行中', value: 'running' },
              { label: '处理中', value: 'streaming' },
              { label: '已完成', value: 'succeeded' },
              { label: '失败', value: 'failed' },
              { label: '已取消', value: 'cancelled' },
            ]}
          />
          <Select
            allowClear
            placeholder="按任务类型筛选"
            style={{ minWidth: 220 }}
            value={taskKindFilter}
            onChange={(value) => {
              setTaskKindFilter(value)
              setPage(1)
            }}
            options={taskKindOptions}
          />
        </div>
        <Table
          rowKey="task_id"
          loading={loading}
          columns={columns}
          dataSource={items}
          locale={{ emptyText: <Empty description="当前没有任务记录" /> }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage)
              setPageSize(nextPageSize)
            },
          }}
          scroll={{ x: 1380 }}
        />
      </Card>
    </div>
  )
}
