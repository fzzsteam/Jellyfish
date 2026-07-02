import { Card, Empty, Typography } from 'antd'
import type { ShotRead } from '../../../../services/generated'
import { buildFileDownloadUrl } from '../../assets/utils'

type ShotVideoResultsTabProps = {
  shot: ShotRead | null
}

/**
 * 展示当前镜头已生成的视频结果。
 * 结果文件沿用现有文件下载地址，不引入新的后端接口。
 */
export function ShotVideoResultsTab({ shot }: ShotVideoResultsTabProps) {
  const fileId = shot?.generated_video_file_id?.trim()
  const videoUrl = buildFileDownloadUrl(fileId)

  if (!fileId || !videoUrl) {
    return <Empty description="当前镜头还没有已生成视频" />
  }

  return (
    <Card title="视频结果">
      <div className="space-y-3">
        <video
          src={videoUrl}
          controls
          className="w-full max-h-[520px] rounded-lg bg-black"
        >
          当前浏览器不支持视频播放。
        </video>
        <Typography.Text type="secondary" className="text-xs">
          文件 ID：{fileId}
        </Typography.Text>
      </div>
    </Card>
  )
}
