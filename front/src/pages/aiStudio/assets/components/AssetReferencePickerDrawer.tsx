/**
 * AssetReferencePickerDrawer — 资产编辑页专用的参考图选择抽屉
 *
 * 在资产编辑页新增/替换参考图时弹出。右侧半屏 Drawer，按角色/演员/场景/道具/服装
 * 5 种资产类型分 tab 展示资产库列表，支持搜索；选中后直接从列表项的 thumbnail
 * 字段解析出 file_id 并回调，不需要再单独请求资产详情。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Drawer, Empty, Input, Segmented, Spin, message } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { StudioEntitiesService } from '../../../../services/generated'
import { resolveAssetUrl, tryExtractFileIdFromUrl } from '../utils'

export type AssetReferenceKind = 'character' | 'actor' | 'scene' | 'prop' | 'costume'

export type AssetReferenceOption = {
  kind: AssetReferenceKind
  entityId: string
  entityName: string
  file_id: string
}

type PickerItem = {
  id: string
  name: string
  thumbnail?: string | null
  description?: string | null
}

const KIND_LABEL: Record<AssetReferenceKind, string> = {
  character: '角色',
  actor: '演员',
  scene: '场景',
  prop: '道具',
  costume: '服装',
}

const KIND_OPTIONS: Array<{ label: string; value: AssetReferenceKind }> = [
  { label: '角色', value: 'character' },
  { label: '演员', value: 'actor' },
  { label: '场景', value: 'scene' },
  { label: '道具', value: 'prop' },
  { label: '服装', value: 'costume' },
]

const PAGE_SIZE = 20

// 从资产列表接口返回的 thumbnail 字段（可能是下载 URL、或裸 file_id）里解析出 file_id。
function resolveFileId(thumbnail?: string | null): string | null {
  if (!thumbnail) return null
  return tryExtractFileIdFromUrl(thumbnail) ?? (!thumbnail.includes('/') && !thumbnail.includes(':') ? thumbnail : null)
}

type AssetReferencePickerDrawerProps = {
  open: boolean
  /** 抽屉打开时默认选中的资产类型 tab；替换场景可传入被替换项的 kind。 */
  initialKind?: AssetReferenceKind
  onSelect: (option: AssetReferenceOption) => void
  onClose: () => void
}

export function AssetReferencePickerDrawer({
  open,
  initialKind = 'scene',
  onSelect,
  onClose,
}: AssetReferencePickerDrawerProps) {
  const [activeKind, setActiveKind] = useState<AssetReferenceKind>(initialKind)
  const [searchText, setSearchText] = useState('')
  const [items, setItems] = useState<PickerItem[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [fetching, setFetching] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const searchTimerRef = useRef<number | null>(null)

  const fetchItems = useCallback(
    async (kind: AssetReferenceKind, q: string, p: number, append: boolean) => {
      setFetching(true)
      try {
        const res = await StudioEntitiesService.listEntitiesApiV1StudioEntitiesEntityTypeGet({
          entityType: kind,
          q: q || null,
          page: p,
          pageSize: PAGE_SIZE,
          projectId: null,
        })
        const data = res.data
        if (!data) return
        const mapped: PickerItem[] = (data.items ?? []).map((raw: Record<string, unknown>) => ({
          id: String(raw.id ?? ''),
          name: String(raw.name ?? ''),
          thumbnail: (raw.thumbnail as string | null) ?? null,
          description: (raw.description as string | null) ?? null,
        }))
        setItems((prev) => (append ? [...prev, ...mapped] : mapped))
        setTotal(data.pagination?.total ?? 0)
        setPage(p)
      } catch {
        // 静默失败，保留上一次的列表状态
      } finally {
        setFetching(false)
      }
    },
    [],
  )

  // 每次打开或 initialKind 变更时重置到默认 tab 并清空筛选状态。
  useEffect(() => {
    if (!open) return
    setActiveKind(initialKind)
    setSearchText('')
    setSelectedId(null)
    setPage(1)
    setItems([])
  }, [open, initialKind])

  // 资产类型切换时重新拉取列表。
  useEffect(() => {
    if (!open) return
    setSearchText('')
    setSelectedId(null)
    setPage(1)
    setItems([])
    fetchItems(activeKind, '', 1, false)
  }, [open, activeKind, fetchItems])

  const handleSearch = (val: string) => {
    setSearchText(val)
    if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current)
    searchTimerRef.current = window.setTimeout(() => {
      setItems([])
      setPage(1)
      fetchItems(activeKind, val, 1, false)
    }, 400)
  }

  const handleLoadMore = () => {
    fetchItems(activeKind, searchText, page + 1, true)
  }

  const hasMore = items.length < total

  /**
   * 解析选中资产可作为参考图的 file_id。
   * 列表 thumbnail 有时只是展示 URL，无法稳定反解 file_id；新建资产生成图后尤其容易出现
   * thumbnail 未同步但图片表已有 file_id 的情况，因此确认时兜底读取实体图片列表。
   */
  const resolveReferenceFileId = async (item: PickerItem): Promise<string | null> => {
    const fromThumbnail = resolveFileId(item.thumbnail)
    if (fromThumbnail) return fromThumbnail

    const res = await StudioEntitiesService.listEntityImagesApiV1StudioEntitiesEntityTypeEntityIdImagesGet({
      entityType: activeKind,
      entityId: item.id,
      order: 'updated_at',
      isDesc: true,
      page: 1,
      pageSize: 20,
    })
    const imageItems = (res.data?.items ?? []) as Array<Record<string, unknown>>
    const matched = imageItems.find((image) => typeof image.file_id === 'string' && image.file_id.trim())
    return typeof matched?.file_id === 'string' ? matched.file_id.trim() : null
  }

  const handleConfirm = async () => {
    if (!selectedId) return
    const item = items.find((i) => i.id === selectedId)
    if (!item) return
    setConfirming(true)
    try {
      const fileId = await resolveReferenceFileId(item)
      if (!fileId) {
        message.warning('该资产暂无可用图片，无法作为参考图')
        return
      }
      onSelect({ kind: activeKind, entityId: item.id, entityName: item.name, file_id: fileId })
    } finally {
      setConfirming(false)
    }
  }

  return (
    <Drawer
      title="添加参考图"
      placement="right"
      width="50%"
      open={open}
      onClose={onClose}
      destroyOnClose
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" disabled={!selectedId} loading={confirming} onClick={() => void handleConfirm()}>
            确认添加
          </Button>
        </div>
      }
    >
      <div className="flex flex-col h-full gap-4">
        <Segmented
          block
          value={activeKind}
          onChange={(value) => setActiveKind(value as AssetReferenceKind)}
          options={KIND_OPTIONS}
        />

        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={`搜索${KIND_LABEL[activeKind]}名称或描述`}
          value={searchText}
          onChange={(e) => handleSearch(e.target.value)}
          allowClear
        />

        {fetching && items.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <Spin />
          </div>
        ) : items.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <Empty description={`暂无${KIND_LABEL[activeKind]}资产`} />
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {items.map((item) => {
                const isSelected = selectedId === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(isSelected ? null : item.id)}
                    className={[
                      'relative flex flex-col rounded-lg border-2 overflow-hidden text-left transition-all cursor-pointer',
                      isSelected
                        ? 'border-blue-500 shadow-md ring-2 ring-blue-200'
                        : 'border-slate-200 hover:border-slate-400',
                    ].join(' ')}
                  >
                    <div className="w-full aspect-square bg-slate-100 overflow-hidden">
                      {item.thumbnail ? (
                        <img
                          src={resolveAssetUrl(item.thumbnail) ?? ''}
                          alt={item.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">
                          暂无图片
                        </div>
                      )}
                    </div>
                    <div className="px-2 py-1.5">
                      <div className="text-xs font-medium text-slate-800 truncate">{item.name}</div>
                      {item.description ? (
                        <div className="text-[11px] text-slate-500 truncate mt-0.5">{item.description}</div>
                      ) : null}
                    </div>
                    {isSelected ? (
                      <div className="absolute top-1.5 left-1.5 bg-blue-500 text-white text-[10px] rounded px-1 py-0.5 leading-tight">
                        已选
                      </div>
                    ) : null}
                  </button>
                )
              })}
            </div>

            {hasMore ? (
              <div className="mt-4 flex justify-center">
                <Button size="small" loading={fetching} onClick={handleLoadMore}>
                  加载更多（还剩 {total - items.length}）
                </Button>
              </div>
            ) : null}

            {fetching && items.length > 0 ? (
              <div className="mt-4 flex justify-center">
                <Spin size="small" />
              </div>
            ) : null}
          </div>
        )}
      </div>
    </Drawer>
  )
}
