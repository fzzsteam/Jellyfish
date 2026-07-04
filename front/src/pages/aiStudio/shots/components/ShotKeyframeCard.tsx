import { Button, Empty, Image, Tag } from 'antd'
import type { ShotFrameType } from '../../../../services/generated'

/** 单个候选缩略图：来自某帧位的历史生成图片关联记录。 */
export type ShotKeyframeCandidate = {
  linkId: number
  fileId: string
  thumbUrl: string
}

const FRAME_TYPE_LABEL: Record<ShotFrameType, string> = { first: '首帧', key: '关键帧', last: '尾帧' }

type ShotKeyframeCardProps = {
  frameType: ShotFrameType
  currentFileId: string | null
  candidates: ShotKeyframeCandidate[]
  applyingFileId: string | null
  onGenerate: (frameType: ShotFrameType) => void
  onApply: (frameType: ShotFrameType, fileId: string) => void
}

/** 单个帧类型（首帧/关键帧/尾帧）卡片：候选缩略图横向列表 + 生成 + 使用。 */
export function ShotKeyframeCard({
  frameType,
  currentFileId,
  candidates,
  applyingFileId,
  onGenerate,
  onApply,
}: ShotKeyframeCardProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white/80 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-900">{FRAME_TYPE_LABEL[frameType]}</div>
        <Button size="small" onClick={() => onGenerate(frameType)}>
          生成
        </Button>
      </div>
      {candidates.length === 0 ? (
        <Empty description="暂无候选图片" image={Empty.PRESENTED_IMAGE_SIMPLE} imageStyle={{ height: 40 }} />
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {candidates.map((candidate) => {
            const isCurrent = candidate.fileId === currentFileId
            return (
              <div key={candidate.linkId} className="shrink-0 space-y-1">
                <Image src={candidate.thumbUrl} width={72} height={72} className="rounded-md object-cover" />
                {isCurrent ? (
                  <Tag color="blue" className="!m-0 text-center block">
                    使用中
                  </Tag>
                ) : (
                  <Button
                    size="small"
                    block
                    loading={applyingFileId === candidate.fileId}
                    onClick={() => onApply(frameType, candidate.fileId)}
                  >
                    使用
                  </Button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
