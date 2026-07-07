import { useEffect, useState } from 'react'
import { ArrowLeftOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Card, Empty, Form, Input, Layout, Modal, Space, Spin, Typography, message } from 'antd'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { StudioChaptersService, StudioShotsService } from '../../../services/generated'
import { generateUUID } from '../../../utils'
import {
  getChapterShotDetailPath,
  getProjectWorkbenchPath,
  type ShotDetailTabKey,
} from '../project/ProjectWorkbench/routes'

const { Header, Content } = Layout

type ChapterShotEntryPageProps = {
  preferredTab?: ShotDetailTabKey
}

/**
 * 章节分镜入口：替代旧分镜列表页和旧生成入口。
 *
 * 有镜头时直接进入首个分镜详情；空章节时只提供创建第一条分镜的最小入口，
 * 详情页继续承载后续准备、生成和结果查看流程。
 */
export function ChapterShotEntryPage({ preferredTab = 'basic' }: ChapterShotEntryPageProps) {
  const navigate = useNavigate()
  const { projectId, chapterId } = useParams<{ projectId: string; chapterId: string }>()
  const [loading, setLoading] = useState(true)
  const [chapterTitle, setChapterTitle] = useState('')
  const [chapterIndex, setChapterIndex] = useState<number | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [createSubmitting, setCreateSubmitting] = useState(false)
  const [createForm] = Form.useForm<{ title: string; script_excerpt?: string }>()

  useEffect(() => {
    if (!projectId || !chapterId) return

    let cancelled = false

    const loadEntry = async () => {
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
        if (cancelled) return

        const chapter = chapterRes.data
        setChapterTitle(chapter?.title ?? '')
        setChapterIndex(typeof chapter?.index === 'number' ? chapter.index : null)

        const firstShot = shotsRes.data?.items?.[0]
        if (firstShot) {
          navigate(getChapterShotDetailPath(projectId, chapterId, firstShot.id, preferredTab), { replace: true })
        }
      } catch {
        if (!cancelled) {
          message.error('加载分镜入口失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadEntry()

    return () => {
      cancelled = true
    }
  }, [chapterId, navigate, preferredTab, projectId])

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
            <Empty
              description="当前章节还没有分镜"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Space>
                <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(getProjectWorkbenchPath(projectId))}>
                  返回项目工作台
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                  新增第一条分镜
                </Button>
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
    </Layout>
  )
}
