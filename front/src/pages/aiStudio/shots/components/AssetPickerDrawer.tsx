/**
 * AssetPickerDrawer — 资产替换选择抽屉
 *
 * 在准备页中，当用户点击已关联资产卡片上的"替换"按钮时弹出。
 * 右侧半屏 Drawer，展示对应类型（角色/场景/道具/服装）的资产库列表，
 * 支持搜索，选中后触发替换回调。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Drawer, Empty, Input, Spin } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { StudioEntitiesService } from '../../../../services/generated'
import { resolveAssetUrl } from '../../assets/utils'

type AssetKind = 'scene' | 'actor' | 'prop' | 'costume'

/** 资产条目的最小结构（从实体列表接口动态解析） */
type PickerItem = {
  id: string
  name: string
  thumbnail?: string | null
  description?: string | null
}

/** 资产类型 → entity_type 参数映射 */
function kindToEntityType(kind: AssetKind): string {
  return kind === 'actor' ? 'character' : kind
}

/** 类型中文标签 */
function kindLabel(kind: AssetKind): string {
  const map: Record<AssetKind, string> = {
    scene: '场景',
    actor: '角色',
    prop: '道具',
    costume: '服装',
  }
  return map[kind]
}

type AssetPickerDrawerProps = {
  /** 是否打开 */
  open: boolean
  /** 资产类型 */
  kind: AssetKind
  /** 当前已关联的实体 ID（replace 模式下高亮标记） */
  currentEntityId?: string | null
  /** 项目 ID（角色类型需要按项目过滤） */
  projectId: string
  /** 选中某资产后的回调，传入实体 id 与名称 */
  onSelect: (newEntityId: string, newEntityName: string) => void
  /** 关闭抽屉 */
  onClose: () => void
  /** 是否正在提交请求 */
  loading?: boolean
  /** replace（替换已关联）| add（新增关联）；默认 replace */
  mode?: 'replace' | 'add'
}

/**
 * 带搜索和分页加载的资产选择抽屉。
 * 资产数据从 StudioEntitiesService.listEntitiesApiV1StudioEntitiesEntityTypeGet 获取。
 */
export function AssetPickerDrawer({
  open,
  kind,
  currentEntityId,
  projectId,
  onSelect,
  onClose,
  loading = false,
  mode = 'replace',
}: AssetPickerDrawerProps) {
  const [searchText, setSearchText] = useState('')
  const [items, setItems] = useState<PickerItem[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [fetching, setFetching] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const searchTimerRef = useRef<number | null>(null)
  const PAGE_SIZE = 20

  const fetchItems = useCallback(
    async (q: string, p: number, append: boolean) => {
      setFetching(true)
      try {
        const entityType = kindToEntityType(kind)
        const res = await StudioEntitiesService.listEntitiesApiV1StudioEntitiesEntityTypeGet({
          entityType,
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
        // 静默失败
      } finally {
        setFetching(false)
      }
    },
    [kind, projectId],
  )

  // 每次打开或 kind 变更时重置并拉取
  useEffect(() => {
    if (!open) return
    setSearchText('')
    setSelectedId(null)
    setPage(1)
    setItems([])
    fetchItems('', 1, false)
  }, [open, kind, fetchItems])

  // 搜索防抖
  const handleSearch = (val: string) => {
    setSearchText(val)
    if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current)
    searchTimerRef.current = window.setTimeout(() => {
      setItems([])
      setPage(1)
      fetchItems(val, 1, false)
    }, 400)
  }

  const handleLoadMore = () => {
    fetchItems(searchText, page + 1, true)
  }

  const hasMore = items.length < total

  const handleConfirm = () => {
    if (!selectedId) return
    const item = items.find((i) => i.id === selectedId)
    if (!item) return
    onSelect(selectedId, item.name)
  }

  const drawerTitle = mode === 'add'
    ? `添加${kindLabel(kind)}关联`
    : `选择${kindLabel(kind)}（替换当前关联）`
  const confirmLabel = mode === 'add' ? '确认关联' : '确认替换'
  const confirmDisabled = !selectedId || (mode === 'replace' && selectedId === currentEntityId)

  return (
    <Drawer
      title={drawerTitle}
      placement="right"
      width="50%"
      open={open}
      onClose={onClose}
      destroyOnClose
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            disabled={confirmDisabled}
            loading={loading}
            onClick={handleConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      }
    >
      <div className="flex flex-col h-full gap-4">
        {/* 搜索栏 */}
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={`搜索${kindLabel(kind)}名称或描述`}
          value={searchText}
          onChange={(e) => handleSearch(e.target.value)}
          allowClear
        />

        {/* 资产网格 */}
        {fetching && items.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <Spin />
          </div>
        ) : items.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <Empty description={`暂无${kindLabel(kind)}资产`} />
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {items.map((item) => {
                const isSelected = selectedId === item.id
                const isCurrent = item.id === currentEntityId
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
                    {/* 缩略图 */}
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

                    {/* 名称 */}
                    <div className="px-2 py-1.5">
                      <div className="text-xs font-medium text-slate-800 truncate">{item.name}</div>
                      {item.description ? (
                        <div className="text-[11px] text-slate-500 truncate mt-0.5">{item.description}</div>
                      ) : null}
                    </div>

                    {/* 当前关联标记 */}
                    {isCurrent ? (
                      <div className="absolute top-1.5 right-1.5 bg-blue-500 text-white text-[10px] rounded px-1 py-0.5 leading-tight">
                        当前
                      </div>
                    ) : null}

                    {/* 选中标记 */}
                    {isSelected ? (
                      <div className="absolute top-1.5 left-1.5 bg-blue-500 text-white text-[10px] rounded px-1 py-0.5 leading-tight">
                        已选
                      </div>
                    ) : null}
                  </button>
                )
              })}
            </div>

            {/* 加载更多 */}
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
