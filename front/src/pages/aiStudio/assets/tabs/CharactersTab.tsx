import { useEffect, useMemo, useState } from 'react'
import { Button, Col, Empty, Input, Modal, Pagination, Row, Space, Tag, Upload, message } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { StudioEntitiesApi } from '../../../../services/studioEntities'
import { resolveAssetUrl } from '../utils'
import { DisplayImageCard } from '../components/DisplayImageCard'
import { useProjectStyleOptions } from '../../project/useProjectStyleOptions'
import { bulkUploadAssetImages } from '../bulkUploadAssets'
import { generateUUID } from '../../../../utils'

export function CharactersTab() {
  const navigate = useNavigate()
  const { defaultVisualStyle, getDefaultStyle } = useProjectStyleOptions()

  const [characters, setCharacters] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize] = useState(12)
  const [total, setTotal] = useState(0)

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')
  const [previewTitle, setPreviewTitle] = useState('')

  const load = async (opts?: { page?: number; q?: string }) => {
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
    void load({ page: 1 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void load()
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


  /** 创建最小角色资产后进入编辑页，保持与其他资产库新建按钮的工作流一致。 */
  const openCreate = async () => {
    setCreating(true)
    try {
      const created = await StudioEntitiesApi.create('character', {
        id: generateUUID(),
        name: `未命名角色-${Date.now().toString(36)}`,
        description: '',
        tags: [],
        view_count: 1,
        visual_style: defaultVisualStyle,
        style: getDefaultStyle(defaultVisualStyle),
        prompt_template_id: null,
      })
      const createdId = String((created.data as { id?: string } | undefined)?.id ?? '')
      if (!createdId) throw new Error('missing created character id')
      navigate(`/assets/characters/${createdId}/edit`)
    } catch {
      message.error('创建角色资产失败')
    } finally {
      setCreating(false)
    }
  }

  /** 批量上传图片：每张图按文件名创建一个角色，并写入正面图槽位。 */
  const handleBulkUpload = async (files: File[]) => {
    if (files.length === 0) return
    setUploading(true)
    try {
      const result = await bulkUploadAssetImages({
        entityType: 'character',
        files,
        visualStyle: defaultVisualStyle,
        style: getDefaultStyle(defaultVisualStyle),
      })
      if (result.createdCount > 0) {
        setPage(1)
        await load({ page: 1 })
      }
      if (result.createdCount > 0 && result.failedCount === 0) {
        message.success(`已创建 ${result.createdCount} 个角色资产`)
      } else if (result.createdCount > 0) {
        message.warning(`已创建 ${result.createdCount} 个角色资产，${result.failedCount} 个文件失败`)
      } else {
        message.error('批量上传失败')
      }
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input.Search
          placeholder="搜索角色名称、描述或标签"
          allowClear
          className="max-w-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onSearch={() => {
            setPage(1)
            void load({ page: 1 })
          }}
        />
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} loading={creating} onClick={() => void openCreate()}>
            新建角色
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
      </div>

      {!loading && characters.length === 0 ? (
        <Empty description="暂无角色资产" />
      ) : (
        <div className={`min-h-[200px] ${loading ? 'opacity-50' : ''}`}>
          <Row gutter={[16, 16]}>
            {filtered.length === 0 ? (
              <Col span={24}>
                <div className="text-center text-gray-500 py-8">
                  {search ? '无匹配角色' : '暂无角色'}
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
      )}

      <Modal
        title={previewTitle}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={880}
      >
        <div className="w-full flex justify-center bg-gray-50 rounded-md overflow-hidden">
          <img src={previewUrl} alt={previewTitle} className="block max-w-full max-h-[70vh] object-contain" />
        </div>
      </Modal>
    </div>
  )
}
