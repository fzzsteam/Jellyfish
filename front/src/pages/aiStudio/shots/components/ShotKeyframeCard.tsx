import { Button, Image, Tooltip } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { ShotFrameType } from '../../../../services/generated'

/** 单个候选缩略图：来自某帧位的历史生成图片关联记录。 */
export type ShotKeyframeCandidate = {
  linkId: number
  fileId: string
  thumbUrl: string
}

const FRAME_TYPE_LABEL: Record<ShotFrameType, string> = { first: '首帧', key: '关键帧', last: '尾帧' }
const FRAME_TYPE_TONE: Record<ShotFrameType, { border: string; bg: string; label: string }> = {
  first: { border: 'border-sky-200', bg: 'bg-sky-50/60', label: 'text-sky-700' },
  key: { border: 'border-violet-200', bg: 'bg-violet-50/60', label: 'text-violet-700' },
  last: { border: 'border-emerald-200', bg: 'bg-emerald-50/60', label: 'text-emerald-700' },
}

type ShotKeyframeCardProps = {
  frameType: ShotFrameType
  currentFileId: string | null
  candidates: ShotKeyframeCandidate[]
  applyingFileId: string | null
  onGenerate: (frameType: ShotFrameType) => void
  onApply: (frameType: ShotFrameType, fileId: string) => void
}

/**
 * 单个帧位卡片：展示当前使用图片、历史候选与生成入口。
 * 该卡片服务于视频生成 Tab 的参考帧区，强调“当前帧位是否已选定”。
 */
export function ShotKeyframeCard({
  frameType,
  currentFileId,
  candidates,
  applyingFileId,
  onGenerate,
  onApply,
}: ShotKeyframeCardProps) {
  const currentCandidate = candidates.find((candidate) => candidate.fileId === currentFileId) ?? null
  const otherCandidates = candidates.filter((candidate) => candidate.fileId !== currentFileId)
  const orderedCandidates = currentCandidate ? [currentCandidate, ...otherCandidates] : otherCandidates
  const hasCurrentFileOutsideCandidates = !!currentFileId && !currentCandidate
  const tone = FRAME_TYPE_TONE[frameType]

  return (
    <div className={`w-full min-w-0 rounded-md border ${tone.border} ${tone.bg} px-2 py-2`}>
      <div className="flex w-full items-center gap-2">
        <div className="w-14 shrink-0">
          <div className={`text-xs font-semibold ${tone.label}`}>{FRAME_TYPE_LABEL[frameType]}</div>
          <div className="mt-0.5 text-[10px] leading-3 text-slate-500">
            {candidates.length > 0 ? `${candidates.length} 张` : '暂无'}
          </div>
        </div>

        <div className="min-w-0 flex-1">
          {hasCurrentFileOutsideCandidates ? (
            <div className="mb-1 rounded border border-blue-100 bg-blue-50 px-2 py-0.5 text-[10px] text-blue-700">
              当前已选图片不在候选中
            </div>
          ) : null}
          {orderedCandidates.length === 0 ? (
            <div className="flex h-[48px] items-center justify-center rounded border border-dashed border-slate-200 bg-white/70 text-[11px] text-slate-400">
              暂无候选
            </div>
          ) : (
            <div className="flex w-full gap-1.5 overflow-x-auto py-0.5">
              {orderedCandidates.map((candidate) => {
                const isCurrent = candidate.fileId === currentFileId
                return (
                  <div
                    key={candidate.linkId}
                    className={[
                      'relative h-[48px] w-[48px] shrink-0 overflow-hidden rounded border bg-slate-100 shadow-sm',
                      isCurrent ? 'border-blue-500 ring-2 ring-blue-200' : 'border-white hover:border-slate-300',
                    ].join(' ')}
                  >
                    <Image
                      src={candidate.thumbUrl}
                      width={48}
                      height={48}
                      className="object-cover"
                      preview={{ mask: '预览' }}
                    />
                    {isCurrent ? (
                      <span className="absolute left-0.5 top-0.5 rounded bg-blue-600 px-1 text-[9px] font-medium leading-[14px] text-white shadow-sm">
                        已选
                      </span>
                    ) : (
                      <Tooltip title="设为当前参考图">
                        <button
                          type="button"
                          className="absolute inset-x-0 bottom-0 bg-slate-900/75 py-[1px] text-[9px] text-white opacity-90 transition hover:bg-blue-600 hover:opacity-100"
                          disabled={applyingFileId === candidate.fileId}
                          onClick={() => onApply(frameType, candidate.fileId)}
                        >
                          {applyingFileId === candidate.fileId ? '设置中' : '使用'}
                        </button>
                      </Tooltip>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <Button size="small" icon={<PlusOutlined />} onClick={() => onGenerate(frameType)}>
          生成
        </Button>
      </div>
    </div>
  )
}
