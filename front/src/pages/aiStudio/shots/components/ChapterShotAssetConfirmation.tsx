import { Button, Popconfirm, Tag, Tooltip } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { DisplayImageCard } from '../../assets/components/DisplayImageCard'
import { resolveAssetUrl } from '../../assets/utils'
import type {
  EntityNameExistenceItem,
  ShotAssetOverviewItem,
  ShotExtractionSummaryRead,
} from '../../../../services/generated'

type AssetKind = 'scene' | 'actor' | 'prop' | 'costume'
type AssetVM = {
  name: string
  thumbnail?: string | null
  id?: string | null
  file_id?: string | null
  description?: string | null
  kind: AssetKind
  /**
   * linked     = 已关联（无论是否有图片）
   * generating = 已关联，图片生成任务进行中
   * new        = 待确认候选
   */
  status: 'linked' | 'generating' | 'new'
  candidateId?: number
  candidateStatus?: ShotAssetOverviewItem['candidate_status']
}

type ChapterShotAssetConfirmationProps = {
  projectId: string
  extraction: ShotExtractionSummaryRead
  unionAssets: Record<AssetKind, AssetVM[]>
  expandedKinds: Record<AssetKind, boolean>
  candidateActionIds: Record<number, boolean>
  existenceByKindName: Record<AssetKind, Record<string, EntityNameExistenceItem>>
  onToggleExpanded: (kind: AssetKind) => void
  onIgnoreCandidate: (asset: AssetVM) => void
  onHandleNewAsset: (asset: AssetVM) => void
  /** 点击"替换"按钮时触发，传入待替换的资产 */
  onReplaceAsset: (asset: AssetVM) => void
  /** 点击"忽略"按钮确认后触发，解除该资产的关联 */
  onUnlinkAsset: (asset: AssetVM) => void
  /** 正在忽略（解关联）的资产 ID 集合，用于按钮 loading 状态 */
  unlinkingIds: Record<string, boolean>
  /** 点击"添加关联资产"按钮时触发，传入类别 */
  onAddAsset: (kind: AssetKind) => void
}

function assetDetailUrl(kind: AssetKind, id: string, projectId: string) {
  if (kind === 'scene') return `/assets/scenes/${encodeURIComponent(id)}/edit`
  if (kind === 'prop') return `/assets/props/${encodeURIComponent(id)}/edit`
  if (kind === 'costume') return `/assets/costumes/${encodeURIComponent(id)}/edit`
  return `/projects/${encodeURIComponent(projectId)}/roles/${encodeURIComponent(id)}/edit`
}

export function ChapterShotAssetConfirmation({
  projectId,
  extraction,
  unionAssets,
  expandedKinds,
  candidateActionIds,
  existenceByKindName,
  onToggleExpanded,
  onIgnoreCandidate,
  onHandleNewAsset,
  onReplaceAsset,
  onUnlinkAsset,
  unlinkingIds,
  onAddAsset,
}: ChapterShotAssetConfirmationProps) {
  const pendingCount = Object.values(unionAssets).reduce(
    (sum, items) => sum + items.filter((item) => item.status === 'new').length,
    0,
  )
  const assetStatus = (() => {
    if (extraction.state === 'skipped') {
      return { text: '已跳过', color: 'blue' as const }
    }
    if (extraction.state === 'not_extracted') {
      return { text: '未提取', color: 'gold' as const }
    }
    if ((extraction.asset_candidate_total ?? 0) === 0 && extraction.state === 'extracted_empty') {
      return { text: '已提取无候选', color: 'default' as const }
    }
    if (pendingCount > 0) {
      return { text: `待处理 ${pendingCount}`, color: 'gold' as const }
    }
    return { text: '已完成', color: 'green' as const }
  })()

  const emptyStateText =
    extraction.state === 'skipped'
      ? '当前镜头已标记为无需提取，资产候选已按完成处理'
      : extraction.state === 'not_extracted'
        ? '当前还没有自动准备结果，可使用上方“重新提取/刷新候选”修复'
        : extraction.state === 'extracted_empty'
          ? '已执行提取，但当前没有识别到资产候选'
          : '当前没有待确认的资产候选'

  const renderAssetCard = (asset: AssetVM) => {
    const existence = existenceByKindName[asset.kind][asset.name]
    const actionLabel = existence ? (existence.exists ? '关联' : '新建') : '…'
    const candidateBusy = asset.candidateId ? !!candidateActionIds[asset.candidateId] : false
    const isLinked = asset.status === 'linked' || asset.status === 'generating'
    const unlinkBusy = isLinked && !!asset.id && !!unlinkingIds[asset.id]

    // "忽略"按钮（解除关联）：显示在图片正下方，仅已关联卡片有
    const meta = isLinked && asset.id ? (
      <div className="flex items-center justify-between gap-1 mt-1">
        <div className="text-[11px] text-gray-400 truncate">
          {asset.status === 'generating' ? '图片生成中…' : '已关联'}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Popconfirm
            title="确认忽略该资产关联？"
            description="忽略后该资产与当前镜头的关联将被移除，可重新关联。"
            okText="确认忽略"
            cancelText="取消"
            okButtonProps={{ danger: true, loading: unlinkBusy }}
            onConfirm={() => onUnlinkAsset(asset)}
          >
            <Button size="small" type="text" danger loading={unlinkBusy} className="!text-[11px]">
              忽略
            </Button>
          </Popconfirm>
          <Button size="small" type="primary" className="!text-[11px]" onClick={() => onReplaceAsset(asset)}>
            替换
          </Button>
        </div>
      </div>
    ) : null

    const footer =
      asset.status === 'new' ? (
        <div className="flex items-center justify-between gap-2">
          <div className="text-[11px] text-gray-500 truncate">
            {existence
              ? existence.linked_to_project
                ? '项目内可关联'
                : existence.exists
                  ? '资产库已有'
                  : '需新建'
              : '正在检查…'}
          </div>
          <div className="flex items-center gap-1">
            {asset.candidateId ? (
              <Button
                size="small"
                type="text"
                danger
                loading={candidateBusy}
                onClick={() => onIgnoreCandidate(asset)}
              >
                忽略
              </Button>
            ) : null}
            <Button size="small" disabled={!existence || candidateBusy} onClick={() => onHandleNewAsset(asset)}>
              {actionLabel}
            </Button>
          </div>
        </div>
      ) : null

    return (
      <div key={`${asset.kind}:${asset.name}`} className="col-span-12 md:col-span-6 xl:col-span-3 2xl:col-span-2">
        <DisplayImageCard
          title={
            <div className="flex items-center justify-between gap-2 min-w-0">
              <div className="min-w-0">
                {asset.id ? (
                  <Button
                    type="link"
                    size="small"
                    className="!p-0 !h-auto"
                    onClick={() =>
                      window.open(assetDetailUrl(asset.kind, asset.id!, projectId), '_blank', 'noopener,noreferrer')
                    }
                  >
                    <span className="truncate inline-block max-w-[140px] align-bottom">{asset.name}</span>
                  </Button>
                ) : (
                  <Tooltip title="该资产仅提取结果，尚未落库">
                    <span className="truncate inline-block max-w-[140px] text-gray-400 cursor-not-allowed align-bottom">{asset.name}</span>
                  </Tooltip>
                )}
              </div>
              {asset.status === 'linked' ? (
                <Tag color="blue">已关联</Tag>
              ) : asset.status === 'generating' ? (
                <Tag color="orange">正在生成</Tag>
              ) : (
                <Tag color="magenta">新提取</Tag>
              )}
            </div>
          }
          imageUrl={resolveAssetUrl(asset.thumbnail)}
          imageAlt={asset.name}
          enablePreview
          hoverable={false}
          size="small"
          imageHeightClassName="h-24"
          meta={meta}
          footer={footer}
        />
      </div>
    )
  }

  const renderAssetGrid = (kind: AssetKind, titleLabel: string, items: AssetVM[]) => {
    const linkedItems = items.filter(
      (item) => item.status === 'linked' || item.status === 'generating',
    )
    const candidateItems = items.filter((item) => item.status === 'new')
    const expanded = expandedKinds[kind]
    const linkedVisible = expanded ? linkedItems : linkedItems.slice(0, 6)
    const candidateVisible = expanded ? candidateItems : candidateItems.slice(0, 6)
    const hiddenCount = Math.max(0, linkedItems.length + candidateItems.length - linkedVisible.length - candidateVisible.length)
    return (
      <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs text-gray-600 font-medium">
            {titleLabel}（{items.length}）
          </div>
          <div className="flex items-center gap-1">
            <Button
              type="link"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => onAddAsset(kind)}
              className="!text-[11px]"
            >
              添加关联资产
            </Button>
            {items.length > 12 ? (
              <Button type="link" size="small" onClick={() => onToggleExpanded(kind)}>
                {expanded ? '收起' : `更多（+${hiddenCount}）`}
              </Button>
            ) : null}
          </div>
        </div>
        {items.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-5 text-xs text-slate-500">
            {emptyStateText}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[11px] font-medium text-slate-600">当前已关联（{linkedItems.length}）</div>
                {linkedItems.length > 0 ? <Tag color="blue">当前状态</Tag> : null}
              </div>
              {linkedItems.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-500">
                  当前镜头还没有关联{titleLabel}
                </div>
              ) : (
                <div className="grid grid-cols-12 gap-2">
                  {linkedVisible.map((asset) => renderAssetCard(asset))}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[11px] font-medium text-slate-600">待确认候选（{candidateItems.length}）</div>
                {candidateItems.length > 0 ? <Tag color="magenta">待确认</Tag> : null}
              </div>
              {candidateItems.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-500">
                  当前没有待确认的{titleLabel}候选
                </div>
              ) : (
                <div className="grid grid-cols-12 gap-2">
                  {candidateVisible.map((asset) => renderAssetCard(asset))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white/80 px-4 py-4">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-slate-900 px-1.5 text-[11px] font-semibold text-white">
              2.1
            </span>
            <div className="text-sm font-medium text-slate-900">资产候选确认</div>
            <Tag color={assetStatus.color} className="m-0">
              {assetStatus.text}
            </Tag>
          </div>
          <div className="text-[11px] text-slate-500 mt-1">系统会优先自动关联已有图片资产；这里只处理缺图、低置信或需要新建的候选。</div>
        </div>
      </div>
      <div className="space-y-4">
        {renderAssetGrid('scene', '场景', unionAssets.scene)}
        {renderAssetGrid('actor', '角色', unionAssets.actor)}
        {renderAssetGrid('prop', '道具', unionAssets.prop)}
        {renderAssetGrid('costume', '服装', unionAssets.costume)}
      </div>
    </div>
  )
}
