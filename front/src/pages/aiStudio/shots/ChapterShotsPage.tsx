import { useCallback, useEffect, useState } from 'react'
import {
  ArrowLeftOutlined,
  LoadingOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Divider,
  Form,
  Input,
  Layout,
  Modal,
  Space,
  Typography,
  message,
} from 'antd'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { ScriptProcessingService, StudioChaptersService, StudioShotsService } from '../../../services/generated'
import {
  defaultTaskActionErrorMessage,
  executeAsyncTaskCreate,
  executeTaskCancel,
} from '../components/taskActionHelpers'
import {
  getChapterShotDetailPath,
  getChapterShotsPath,
} from '../project/ProjectWorkbench/routes'
import {
  useCancelableRelationTask,
} from '../project/ProjectWorkbench/chapterDivisionTasks'
import { useRelationTaskNotification } from '../components/taskNotificationHelpers'
import { createTaskSettledReloader } from '../components/taskResultHelpers'
import { useTaskPageContext } from '../components/taskPageContext'
import { TASK_COPY } from '../components/taskCopy'
import { generateUUID } from '../../../utils'
import { usePointsQuote } from '../../../hooks/usePointsQuote'
import { makePointsAwareGetErrorMessage } from '../../../components/points/pointsTaskError'
import { ExtractionConfirmModal } from './components/ExtractionConfirmModal'

const { Header, Content } = Layout

/**
 * 章节分镜入口页：若章节已有镜头则直接进入首个镜头详情，否则只保留提取与新增两个空态入口。
 */
export function ChapterShotsPage() {
  const navigate = useNavigate()
  const { projectId, chapterId } = useParams<{ projectId: string; chapterId: string }>()
  const [loading, setLoading] = useState(true)
  const [chapterTitle, setChapterTitle] = useState('')
  const [chapterIndex, setChapterIndex] = useState<number | null>(null)
  const [chapterRawText, setChapterRawText] = useState('')
  const [chapterCondensedText, setChapterCondensedText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractConfirmOpen, setExtractConfirmOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [createSubmitting, setCreateSubmitting] = useState(false)
  const [chapterDivisionTaskLoading, setChapterDivisionTaskLoading] = useState(false)
  const [createForm] = Form.useForm<{ title: string; script_excerpt?: string }>()

  const taskCopy = TASK_COPY.chapterDivision
  const divideQuote = usePointsQuote({
    businessType: 'script_divide',
    category: 'text',
    modelId: null,
    enabled: !!chapterId,
  })
  const imageQuote = usePointsQuote({
    businessType: 'image_generation',
    category: 'image',
    modelId: null,
    resolutionProfile: 'standard',
    enabled: !!chapterId,
  })

  const refresh = useCallback(async () => {
    if (!projectId || !chapterId) return
    setLoading(true)
    try {
      const [chapterRes, shotsRes] = await Promise.all([
        StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId }),
        StudioShotsService.listShotsApiV1StudioShotsGet({
          chapterId,
          page: 1,
          pageSize: 100,
          order: 'index',
          isDesc: false,
        }),
      ])
      const chapter = chapterRes.data
      setChapterTitle(chapter?.title ?? '')
      setChapterIndex(typeof chapter?.index === 'number' ? chapter.index : null)
      setChapterRawText(chapter?.raw_text?.trim?.() ? chapter.raw_text.trim() : '')
      setChapterCondensedText(chapter?.condensed_text?.trim?.() ? chapter.condensed_text.trim() : '')

      const firstShot = shotsRes.data?.items?.[0]
      if (firstShot) {
        navigate(getChapterShotDetailPath(projectId, chapterId, firstShot.id, 'basic'), { replace: true })
      }
    } catch {
      message.error('加载分镜入口失败')
    } finally {
      setLoading(false)
    }
  }, [chapterId, navigate, projectId])

  const reloadShotsAfterTaskSettled = useCallback(createTaskSettledReloader(refresh), [refresh])
  const {
    task: chapterDivisionTask,
    settledTask: chapterDivisionSettledTask,
    trackTaskData,
    applyCancelData,
  } = useCancelableRelationTask({
    enabled: !!chapterId,
    relationType: 'chapter_division',
    relationEntityId: chapterId,
    onTaskSettled: reloadShotsAfterTaskSettled,
  })

  useTaskPageContext(
    chapterId
      ? [
          {
            relationType: 'chapter_division',
            relationEntityId: chapterId,
          },
        ]
      : [],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  const handleOneClickExtract = useCallback(async () => {
    if (!chapterId) return
    const scriptText = (chapterCondensedText || chapterRawText).trim()
    if (!scriptText) {
      message.error('章节没有可用文本（condensed/raw 为空）')
      return
    }
    setExtracting(true)
    try {
      const freshQuote = await divideQuote.refreshNow()
      const quoteToken = freshQuote?.quote_token ?? null
      if (!freshQuote?.sufficient || !quoteToken) {
        message.warning('积分试算已刷新，请确认积分充足后再提交')
        return
      }
      await executeAsyncTaskCreate({
        request: () =>
          ScriptProcessingService.divideScriptAsyncApiV1ScriptProcessingDivideAsyncPost({
            requestBody: {
              script_text: scriptText,
              write_to_db: true,
              chapter_id: chapterId,
              quote_token: quoteToken,
            },
          }),
        trackTaskData,
        startedMessage: taskCopy.startedMessage,
        reusedMessage: taskCopy.reusedMessage,
        fallbackErrorMessage: '启动分镜提取失败',
        getErrorMessage: makePointsAwareGetErrorMessage(divideQuote.refresh),
      })
    } catch {
      // executeAsyncTaskCreate 已统一处理错误提示
    } finally {
      setExtracting(false)
    }
  }, [chapterCondensedText, chapterId, chapterRawText, divideQuote.refresh, divideQuote.refreshNow, trackTaskData, taskCopy.reusedMessage, taskCopy.startedMessage])

  const handleCancelChapterDivisionTask = useCallback(async () => {
    if (!chapterDivisionTask) return
    setChapterDivisionTaskLoading(true)
    try {
      await executeTaskCancel({
        taskId: chapterDivisionTask.taskId,
        reason: '用户在分镜入口页取消分镜提取',
        applyCancelData,
        cancelledImmediatelyMessage: taskCopy.cancelledImmediatelyMessage,
        cancelRequestedMessage: taskCopy.cancelRequestedMessage,
        fallbackErrorMessage: '取消任务失败',
      })
    } catch {
      // executeTaskCancel 已统一处理错误提示
    } finally {
      setChapterDivisionTaskLoading(false)
    }
  }, [applyCancelData, chapterDivisionTask, taskCopy.cancelRequestedMessage, taskCopy.cancelledImmediatelyMessage])

  useRelationTaskNotification({
    task: chapterDivisionTask,
    settledTask: chapterDivisionSettledTask,
    title: taskCopy.title,
    sourceLabel: chapterTitle ? `章节：${chapterTitle}` : '分镜入口页',
    runningDescription: taskCopy.runningDescription,
    cancellingDescription: taskCopy.cancellingDescription,
    successDescription: taskCopy.successDescription,
    cancelledDescription: taskCopy.cancelledDescription,
    failedDescription: taskCopy.failedDescription,
    onCancel: chapterDivisionTask ? () => void handleCancelChapterDivisionTask() : null,
    onNavigate:
      projectId && chapterId
        ? () => navigate(getChapterShotsPath(projectId, chapterId))
        : null,
  })

  const openCreate = useCallback(() => {
    createForm.resetFields()
    setCreateOpen(true)
  }, [createForm])

  const closeCreate = useCallback(() => {
    setCreateOpen(false)
    createForm.resetFields()
  }, [createForm])

  const submitCreate = useCallback(async () => {
    if (!projectId || !chapterId) return
    try {
      const values = await createForm.validateFields()
      setCreateSubmitting(true)
      const createdRes = await StudioShotsService.createShotApiV1StudioShotsPost({
        requestBody: {
          id: generateUUID(),
          chapter_id: chapterId,
          index: 1,
          title: values.title.trim(),
          script_excerpt: values.script_excerpt?.trim() ? values.script_excerpt.trim() : '',
          status: 'pending',
        },
      })
      const created = createdRes.data
      if (created) {
        message.success('已创建分镜')
        closeCreate()
        navigate(getChapterShotDetailPath(projectId, chapterId, created.id, 'basic'), { replace: true })
      }
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(defaultTaskActionErrorMessage(error, '创建失败'))
    } finally {
      setCreateSubmitting(false)
    }
  }, [chapterId, closeCreate, createForm, navigate, projectId])

  if (!projectId || !chapterId) {
    return <Navigate to="/projects" replace />
  }

  return (
    <Layout style={{ height: '100%', minHeight: 0, background: '#eef2f7' }}>
      <Header
        style={{
          padding: '0 16px',
          background: '#fff',
          borderBottom: '1px solid #e2e8f0',
          boxShadow: '0 2px 4px rgba(0,0,0,0.04)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <Link to={`/projects/${projectId}?tab=chapters`} className="text-gray-600 hover:text-blue-600 flex items-center gap-1">
          <ArrowLeftOutlined />
          返回章节列表
        </Link>
        <Divider type="vertical" />
        <div className="min-w-0 flex-1 overflow-hidden">
          <Typography.Text strong className="truncate block">
            {chapterIndex !== null ? `第${chapterIndex}章 · ${chapterTitle || '未命名'}` : chapterTitle || '章节'}
          </Typography.Text>
          <Typography.Text type="secondary" className="text-xs truncate block">
            分镜入口
          </Typography.Text>
        </div>
      </Header>

      <Content style={{ padding: 16, minHeight: 0 }}>
        <Card
          style={{ maxWidth: 760, margin: '0 auto' }}
          bodyStyle={{ padding: 24 }}
          title="进入分镜"
        >
          {loading ? (
            <div className="flex min-h-[240px] items-center justify-center text-slate-500">
              <Space>
                <LoadingOutlined />
                <span>正在定位分镜详情…</span>
              </Space>
            </div>
          ) : (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Alert
                type="info"
                showIcon
                message="当前章节还没有分镜"
                description="可以先一键提取整章分镜并自动准备，也可以手动新增第一条分镜。章节一旦已有分镜，再进入这里会直接跳到分镜详情页。"
              />

              <Card size="small" title="快捷操作">
                <Space wrap>
                  <Button
                    type="primary"
                    icon={<ReloadOutlined />}
                    loading={extracting}
                    disabled={!!chapterDivisionTask}
                    onClick={() => setExtractConfirmOpen(true)}
                  >
                    一键提取分镜
                  </Button>
                  {chapterDivisionTask ? (
                    <Button
                      icon={<StopOutlined />}
                      loading={chapterDivisionTaskLoading}
                      onClick={() => void handleCancelChapterDivisionTask()}
                    >
                      取消提取
                    </Button>
                  ) : null}
                  <Button icon={<PlusOutlined />} onClick={openCreate}>
                    新增分镜
                  </Button>
                </Space>
              </Card>

              {!chapterRawText.trim() && !chapterCondensedText.trim() ? (
                <Alert
                  type="warning"
                  showIcon
                  message="当前章节还没有可提取文本"
                  description="如果要使用一键提取，请先回章节列表补充原文或 condensed 文本。"
                />
              ) : null}
            </Space>
          )}
        </Card>
      </Content>

      <Modal
        title="新增分镜"
        open={createOpen}
        onCancel={closeCreate}
        onOk={() => void submitCreate()}
        confirmLoading={createSubmitting}
        okText="创建"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="title"
            label="分镜标题"
            rules={[{ required: true, message: '请输入分镜标题' }]}
          >
            <Input maxLength={120} placeholder="例如：主角推门进入房间" />
          </Form.Item>
          <Form.Item name="script_excerpt" label="剧本摘录">
            <Input.TextArea rows={4} maxLength={1000} placeholder="可选，先补一个简短摘录也可以" />
          </Form.Item>
        </Form>
      </Modal>

      <ExtractionConfirmModal
        open={extractConfirmOpen}
        title="确认提取分镜并自动准备"
        onConfirm={() => {
          setExtractConfirmOpen(false)
          void handleOneClickExtract()
        }}
        onCancel={() => setExtractConfirmOpen(false)}
        costRows={[
          {
            label: '分镜拆解 + 信息提取（文本各一次）',
            quote: divideQuote.quote,
            loading: divideQuote.loading,
            textMultiplier: 2,
          },
          { label: '自动关联已有资产', free: true },
          {
            label: '新资产图片生成（每张）',
            quote: imageQuote.quote,
            loading: imageQuote.loading,
            noModel: !imageQuote.loading && !imageQuote.quote ? true : undefined,
          },
        ]}
        note="资产图数量由 AI 拆解后生成的分镜数决定，拆解前无法预知；积分不足时对应资产将建档但不生成图片。"
      />
    </Layout>
  )
}
