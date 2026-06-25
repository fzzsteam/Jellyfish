import { useEffect, useMemo, useState } from 'react'
import { Button, Col, Empty, Input, Modal, Pagination, Row, Select, Space, Tag, message } from 'antd'
import { DeleteOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { StudioEntitiesApi } from '../../../../services/studioEntities'
import { StudioProjectsService } from '../../../../services/generated'
import type { ProjectRead } from '../../../../services/generated'
import { resolveAssetUrl } from '../utils'
import { DisplayImageCard } from '../components/DisplayImageCard'

export function CharactersTab() {
  const navigate = useNavigate()

  const [projects, setProjects] = useState<ProjectRead[]>([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)

  const [characters, setCharacters] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize] = useState(12)
  const [total, setTotal] = useState(0)

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')
  const [previewTitle, setPreviewTitle] = useState('')

  useEffect(() => {
    void (async () => {
      setProjectsLoading(true)
      try {
        const res = await StudioProjectsService.listProjectsApiV1StudioProjectsGet({ page: 1, pageSize: 100 })
        const items = res.data?.items ?? []
        setProjects(items)
        if (items.length > 0) {
          setSelectedProjectId(items[0].id)
        }
      } catch {
        message.error('加载项目列表失败')
      } finally {
        setProjectsLoading(false)
      }
    })()
  }, [])

  const load = async (opts?: { page?: number; q?: string; projectId?: string | null }) => {
    const pid = opts?.projectId !== undefined ? opts.projectId : selectedProjectId
    if (!pid) return
    setLoading(true)
    try {
      const nextPage = opts?.page ?? page
      const q = typeof opts?.q === 'string' ? opts.q : search.trim() || undefined
      const res = await StudioEntitiesApi.list('character', {
        page: nextPage,
        pageSize,
        q: q ?? null,
        order: 'updated_at',
        isDesc: true,
        projectId: pid,
      })
      setCharacters(res.data?.items ?? [])
      setTotal(res.data?.pagination.total ?? 0)
    } catch {
      message.error('加载角色失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (selectedProjectId) {
      setPage(1)
      void load({ page: 1, projectId: selectedProjectId })
    } else {
      setCharacters([])
      setTotal(0)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId])

  useEffect(() => {
    if (selectedProjectId) void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const filtered = useMemo(() => (Array.isArray(characters) ? characters : []), [characters])

  const handleDelete = (asset: any) => {
    Modal.confirm({
      title: '删除角色？',
      content: `将删除「${asset.name}」。`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await StudioEntitiesApi.remove('character', asset.id)
          message.success('已删除')
          void load()
        } catch {
          message.error('删除失败')
        }
      },
    })
  }

  const openPreview = (asset: any) => {
    const url = resolveAssetUrl(asset.thumbnail)
    if (!url) { message.info('未生成图片'); return }
    setPreviewTitle(asset.name)
    setPreviewUrl(url)
    setPreviewOpen(true)
  }

  if (!projectsLoading && projects.length === 0) {
    return <Empty description="暂无项目，请先创建项目后再管理角色" />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Space wrap>
          <Select
            style={{ minWidth: 200 }}
            loading={projectsLoading}
            placeholder="选择项目"
            value={selectedProjectId}
            onChange={(val) => setSelectedProjectId(val)}
            options={projects.map((p) => ({ value: p.id, label: p.name }))}
          />
          <Input.Search
            placeholder="搜索角色名称或描述"
            allowClear
            className="max-w-xs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onSearch={() => { setPage(1); void load({ page: 1 }) }}
          />
        </Space>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
      </div>

      <div className={`min-h-[200px] ${loading ? 'opacity-50' : ''}`}>
        <Row gutter={[16, 16]}>
          {filtered.length === 0 ? (
            <Col span={24}>
              <div className="text-center text-gray-500 py-8">
                {search ? '无匹配角色' : '该项目暂无角色'}
              </div>
            </Col>
          ) : (
            filtered.map((a) => {
              const thumbnailUrl = resolveAssetUrl(a.thumbnail)
              return (
                <Col xs={24} sm={12} md={8} lg={6} key={a.id}>
                  <DisplayImageCard
                    title={<span className="truncate">{a.name}</span>}
                    imageUrl={thumbnailUrl}
                    imageAlt={a.name}
                    placeholder="未生成"
                    onImageClick={() => openPreview(a)}
                    extra={
                      <Button
                        size="small"
                        type="link"
                        icon={<EditOutlined />}
                        onClick={() => navigate(`/assets/characters/${a.id}/edit`)}
                      >
                        编辑
                      </Button>
                    }
                    actions={[
                      <Button
                        type="text"
                        key="del"
                        danger
                        icon={<DeleteOutlined />}
                        size="small"
                        onClick={() => handleDelete(a)}
                      />,
                    ]}
                    meta={
                      <>
                        <div className="text-xs text-gray-500 mb-2 line-clamp-2">{a.description || '暂无描述'}</div>
                        <div className="flex flex-wrap gap-1">
                          {(a.tags ?? []).slice(0, 3).map((t: string) => <Tag key={t}>{t}</Tag>)}
                        </div>
                      </>
                    }
                  />
                </Col>
              )
            })
          )}
        </Row>

        <div className="flex justify-end pt-4">
          <Pagination
            current={page}
            pageSize={pageSize}
            total={total}
            showSizeChanger={false}
            showTotal={(t) => `共 ${t} 条`}
            onChange={(p) => setPage(p)}
          />
        </div>
      </div>

      <Modal
        title={previewTitle}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={880}
      >
        <div className="w-full flex justify-center bg-gray-50 rounded-md overflow-hidden">
          <img src={previewUrl} alt={previewTitle} className="max-h-[70vh] object-contain" />
        </div>
      </Modal>
    </div>
  )
}
