import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Empty, Input, Modal, Pagination, Space, Tag, Upload, message } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import { StudioEntitiesApi } from '../../../../services/studioEntities'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { resolveAssetUrl } from '../utils'
import { DisplayImageCard } from '../components/DisplayImageCard'
import { ActorEntityFormModal, type ActorEntityLike } from '../components/ActorEntityFormModal'
import { useProjectStyleOptions } from '../../project/useProjectStyleOptions'
import { bulkUploadAssetImages } from '../bulkUploadAssets'
import { generateUUID } from '../../../../utils'

export function ActorsTab() {
  const navigate = useNavigate()
  const { defaultVisualStyle, getDefaultStyle } = useProjectStyleOptions()
  const [searchParams, setSearchParams] = useSearchParams()
  const [actors, setActors] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(12)
  const [total, setTotal] = useState(0)

  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<ActorEntityLike | null>(null)
  const [fromShotCreateContext, setFromShotCreateContext] = useState<{
    projectId: string
    chapterId: string
    shotId: string
  } | null>(null)

  const load = async (opts?: { page?: number; pageSize?: number; q?: string }) => {
    setLoading(true)
    try {
      const nextPage = opts?.page ?? page
      const nextPageSize = opts?.pageSize ?? pageSize
      const q = typeof opts?.q === 'string' ? opts.q : search.trim() || undefined
      const res = await StudioEntitiesApi.list('actor', {
        page: nextPage,
        pageSize: nextPageSize,
        q: q ?? null,
        order: 'updated_at',
        isDesc: true,
      })
      const items = res.data?.items ?? []
      setActors(items)
      setTotal(res.data?.pagination.total ?? 0)
    } catch {
      message.error('加载演员失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize])

  useEffect(() => {
    const create = searchParams.get('create')
    const tab = searchParams.get('tab')
    const projectId = searchParams.get('projectId')?.trim() ?? ''
    const chapterId = searchParams.get('chapterId')?.trim() ?? ''
    const shotId = searchParams.get('shotId')?.trim() ?? ''
    if (create === '1' && tab === 'actor') {
      setEditing(null)
      if (projectId && chapterId && shotId) {
        setFromShotCreateContext({ projectId, chapterId, shotId })
      } else {
        setFromShotCreateContext(null)
      }
      setEditOpen(true)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.delete('create')
          next.delete('name')
          next.delete('desc')
          next.delete('projectId')
          next.delete('chapterId')
          next.delete('shotId')
          return next
        },
        { replace: true },
      )
    }
  }, [searchParams, setSearchParams])

  const filtered = useMemo(() => actors, [actors])

  /** 生成唯一草稿名，避免连续新建演员时触发后端名称唯一约束。 */
  const draftActorName = () => `未命名演员-${Date.now().toString(36)}`

  /** 创建一个最小演员草稿并直接进入编辑页，避免列表页和编辑页重复填写基础信息。 */
  const openCreate = async () => {
    setCreating(true)
    try {
      const created = await StudioEntitiesApi.create('actor', {
        id: generateUUID(),
        name: draftActorName(),
        description: '',
        tags: [],
        view_count: 1,
        visual_style: defaultVisualStyle,
        style: getDefaultStyle(defaultVisualStyle),
        prompt_template_id: null,
      })
      const createdId = String((created.data as { id?: string } | undefined)?.id ?? '')
      if (!createdId) throw new Error('missing created actor id')
      navigate(`/assets/actors/${createdId}/edit`)
    } catch {
      message.error('创建演员失败')
    } finally {
      setCreating(false)
    }
  }

  const handleModalCancel = () => {
    setEditOpen(false)
    setEditing(null)
    setFromShotCreateContext(null)
  }

  const handleBulkUpload = async (files: File[]) => {
    if (files.length === 0) return
    setUploading(true)
    try {
      const result = await bulkUploadAssetImages({
        entityType: 'actor',
        files,
        visualStyle: defaultVisualStyle as '现实' | '动漫',
        style: getDefaultStyle(defaultVisualStyle),
      })
      if (result.createdCount > 0) {
        setPage(1)
        await load({ page: 1 })
      }
      if (result.createdCount > 0 && result.failedCount === 0) {
        message.success(`已创建 ${result.createdCount} 个演员资产`)
      } else if (result.createdCount > 0) {
        message.warning(`已创建 ${result.createdCount} 个演员资产，${result.failedCount} 个文件失败`)
      } else {
        message.error('批量上传失败')
      }
    } finally {
      setUploading(false)
    }
  }

  return (
    <Card
      title="演员"
      extra={
        <Space>
          <Input.Search
            placeholder="搜索演员"
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onSearch={(v) => {
              setPage(1)
              void load({ q: v, page: 1 })
            }}
            style={{ width: 240 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} loading={creating} onClick={() => void openCreate()}>
            新建
          </Button>
          <Upload
            accept="image/*"
            multiple
            showUploadList={false}
            disabled={uploading}
            beforeUpload={(file, fileList) => {
              const isLastFile = file.uid === fileList[fileList.length - 1]?.uid
              if (isLastFile) void handleBulkUpload(fileList)
              return Upload.LIST_IGNORE
            }}
          >
            <Button icon={<UploadOutlined />} loading={uploading}>
              批量上传
            </Button>
          </Upload>
        </Space>
      }
    >
      {filtered.length === 0 && !loading ? (
        <Empty description="暂无演员" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {filtered.map((a) => (
            <DisplayImageCard
              key={a.id}
              title={<div className="truncate">{a.name}</div>}
              imageUrl={resolveAssetUrl(a.thumbnail)}
              imageAlt={a.name}
              extra={
                <Button size="small" type="link" icon={<EditOutlined />} onClick={() => navigate(`/assets/actors/${a.id}/edit`)}>
                  编辑
                </Button>
              }
              actions={[
                <Button
                  key="del"
                  type="text"
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={() => {
                    Modal.confirm({
                      title: `删除演员「${a.name}」？`,
                      okText: '删除',
                      cancelText: '取消',
                      okButtonProps: { danger: true },
                      onOk: async () => {
                        try {
                          await StudioEntitiesApi.remove('actor', a.id)
                          message.success('已删除')
                          void load()
                        } catch {
                          message.error('删除失败')
                        }
                      },
                    })
                  }}
                />,
              ]}
              meta={
                <div>
                  {a.description && <div className="text-xs text-gray-600 line-clamp-2">{a.description}</div>}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(a.tags ?? []).slice(0, 6).map((t: string) => (
                      <Tag key={t} className="m-0">
                        {t}
                      </Tag>
                    ))}
                  </div>
                </div>
              }
            />
          ))}
        </div>
      )}

      <div className="mt-4 flex justify-end">
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger={false}
          onChange={(p, ps) => {
            setPage(p)
            setPageSize(ps)
          }}
        />
      </div>

      <ActorEntityFormModal
        open={editOpen}
        editing={editing}
        linkProjectId={fromShotCreateContext?.projectId}
        linkChapterId={fromShotCreateContext?.chapterId}
        linkShotId={fromShotCreateContext?.shotId}
        onCancel={handleModalCancel}
        onSuccess={async (detail) => {
          const createdItem = detail?.created as { id?: string } | undefined
          if (createdItem && page === 1 && !search.trim()) {
            setActors((prev) => [createdItem, ...prev.filter((it) => it.id !== createdItem.id)])
            setTotal((prev) => prev + 1)
          }
          await load({ page: 1 })
          setPage(1)
        }}
      />
    </Card>
  )
}
