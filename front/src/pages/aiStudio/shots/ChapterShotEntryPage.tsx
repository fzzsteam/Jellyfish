import { useCallback, useEffect, useState } from 'react'
import { ArrowLeftOutlined, PlusOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Form, Input, Layout, Modal, Space, Spin, Typography, message } from 'antd'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { ScriptProcessingService, StudioChaptersService, StudioShotsService } from '../../../services/generated'
import { generateUUID } from '../../../utils'
import {
  getChapterShotDetailPath,
  getChapterShotsPath,
  getProjectWorkbenchPath,
  type ShotDetailTabKey,
} from '../project/ProjectWorkbench/routes'
import { useCancelableRelationTask } from '../project/ProjectWorkbench/chapterDivisionTasks'
import { executeAsyncTaskCreate, executeTaskCancel } from '../components/taskActionHelpers'
import { useRelationTaskNotification } from '../components/taskNotificationHelpers'
import { createTaskSettledReloader } from '../components/taskResultHelpers'
import { useTaskPageContext } from '../components/taskPageContext'
import { TASK_COPY } from '../components/taskCopy'
import { usePointsQuote } from '../../../hooks/usePointsQuote'
import { makePointsAwareGetErrorMessage } from '../../../components/points/pointsTaskError'
import { ExtractionConfirmModal } from './components/ExtractionConfirmModal'

const { Header, Content } = Layout

type ChapterShotEntryPageProps = {
  preferredTab?: ShotDetailTabKey
}

/**
 * 章节分镜入口：替代旧分镜列表页和旧生成入口。
 *
 * 有镜头时直接进入首个分镜详情；空章节时提供"一键提取分镜并自动准备"与
 * "手动新增第一条分镜"两个入口，详情页继续承载后续准备、生成和结果查看流程。
 */
export function ChapterShotEntryPage({ preferredTab = 'basic' }: ChapterShotEntryPageProps) {
  const navigate = useNavigate()
  const { projectId, chapterId } = useParams<{ projectId: string; chapterId: string }>()
  const [loading, setLoading] = useState(true)
  const [chapterTitle, setChapterTitle] = useState('')
  const [chapterIndex, setChapterIndex] = useState<number | null>(null)
  const [chapterRawText, setChapterRawText] = useState('')
  const [chapterCondensedText, setChapterCondensedText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractConfirmOpen, setExtractConfirmOpen] = useState(false)
  const [chapterDivisionTaskLoading, setChapterDivisionTaskLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [createSubmitting, setCreateSubmitting] = useState(false)
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

  const loadEntry = useCallback(async () => {
    if (!projectId || !chapterId) return
    setLoading(true)
    try {
      const [chapterRes, shotsRes] = await Promise.all([
        StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId }),
        StudioShotsService.listShotsApiV1StudioShotsGet({
          chapterId,
          page: 1,
          pageSize: 1,
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
        navigate(getChapterShotDetailPath(projectId, chapterId, firstShot.id, preferredTab), { replace: true })
      }
    } catch {
      message.error('加载分镜入口失败')
    } finally {
      setLoading(false)
    }
  }, [chapterId, navigate, preferredTab, projectId])

  useEffect(() => {
    void loadEntry()
  }, [loadEntry])

  const reloadEntryAfterTaskSettled = useCallback(createTaskSettledReloader(loadEntry), [loadEntry])
  const {
    task: chapterDivisionTask,
    settledTask: chapterDivisionSettledTask,
    trackTaskData,
    applyCancelData,
  } = useCancelableRelationTask({
    enabled: !!chapterId,
    relationType: 'chapter_division',
    relationEntityId: chapterId,
    onTaskSettled: reloadEntryAfterTaskSettled,
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

  const openCreate = () => {
    createForm.resetFields()
    setCreateOpen(true)
  }

  const submitCreate = async () => {
    if (!projectId || !chapterId) return

    try {
      const values = await createForm.validateFields()
      setCreateSubmitting(true)
      const res = await StudioShotsService.createShotApiV1StudioShotsPost({
        requestBody: {
          id: generateUUID(),
          chapter_id: chapterId,
          index: 1,
          title: values.title.trim(),
          script_excerpt: values.script_excerpt?.trim() ? values.script_excerpt.trim() : '',
          status: 'pending',
        },
      })
      const created = res.data
      if (!created) {
        message.error('新增分镜失败')
        return
      }
      setCreateOpen(false)
      createForm.resetFields()
      navigate(getChapterShotDetailPath(projectId, chapterId, created.id, 'basic'), { replace: true })
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error('新增分镜失败')
    } finally {
      setCreateSubmitting(false)
    }
  }

  if (!projectId || !chapterId) {
    return <Navigate to="/projects" replace />
  }

  const hasExtractableText = !!chapterRawText.trim() || !!chapterCondensedText.trim()

  return (
    <Layout className="h-full bg-transparent">
      <Header className="bg-white px-4 flex items-center justify-between border-b border-gray-100">
        <div className="min-w-0">
          <Typography.Text strong className="block truncate">
            {chapterIndex !== null ? `第${chapterIndex}章 · ${chapterTitle || '未命名'}` : chapterTitle || '章节'}
          </Typography.Text>
          <Typography.Text type="secondary" className="text-xs block">
            分镜详情入口
          </Typography.Text>
        </div>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(getProjectWorkbenchPath(projectId))}>
          返回项目工作台
        </Button>
      </Header>
      <Content className="p-4">
        <Card>
          {loading ? (
            <div className="flex min-h-[240px] items-center justify-center">
              <Spin size="large" />
            </div>
          ) : (
            <Empty description="当前章节还没有分镜" image={Empty.PRESENTED_IMAGE_SIMPLE}>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Space wrap>
                  <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(getProjectWorkbenchPath(projectId))}>
                    返回项目工作台
                  </Button>
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
                    新增第一条分镜
                  </Button>
                </Space>
                {!hasExtractableText ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="当前章节还没有可提取文本"
                    description="如果要使用一键提取，请先回章节列表补充原文或 condensed 文本。"
                  />
                ) : null}
              </Space>
            </Empty>
          )}
        </Card>
      </Content>
      <Modal
        title="新增第一条分镜"
        open={createOpen}
        onCancel={() => {
          if (createSubmitting) return
          setCreateOpen(false)
          createForm.resetFields()
        }}
        onOk={() => void submitCreate()}
        okText="创建并进入详情"
        cancelText="取消"
        confirmLoading={createSubmitting}
        destroyOnClose
      >
        <Form layout="vertical" form={createForm}>
          <Form.Item
            label="标题"
            name="title"
            rules={[{ required: true, whitespace: true, message: '请输入分镜标题' }]}
          >
            <Input maxLength={120} placeholder="例如：开场远景" />
          </Form.Item>
          <Form.Item label="剧本摘录" name="script_excerpt">
            <Input.TextArea rows={4} maxLength={2000} placeholder="可选，进入详情后仍可继续补充" />
          </Form.Item>
        </Form>
      </Modal>

      <ExtractionConfirmModal
        open={extractConfirmOpen}
        title="确认一键提取分镜并自动准备"
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
