import { useEffect, useRef, useState } from 'react'
import { Button, Card, Empty, Tooltip, message } from 'antd'
import { DownloadOutlined, FullscreenOutlined, VideoCameraOutlined } from '@ant-design/icons'
import type { ShotRead } from '../../../../services/generated'
import { buildFileDownloadUrl } from '../../assets/utils'
import { listTaskLinksNormalized } from '../../../../services/filmTaskLinks'

type GeneratedVideoItem = { linkId: number; fileId: string; url: string }

type ShotVideoResultsTabProps = {
  shot: ShotRead | null
  /** 当前镜头在跨镜头批量下载中选中的视频文件 ID，由详情页统一维护，实现 tab 切换后仍保留选择。 */
  selectedFileId?: string | null
  /** 用户点击卡片选中视频时回调，详情页会据此写回 generated_video_file_id（“当前使用”）并更新批量下载选中态。 */
  onSelectVideo?: (fileId: string) => void
  /** 列表首次加载且尚无选中项时的默认选中回调，仅用于批量下载兜底，不应写回后端“当前使用”。 */
  onDefaultSelectVideo?: (fileId: string) => void
}

/** 切换单个结果卡片内的视频播放状态，方便在网格中直接预览。 */
function toggleVideoPlayback(video: HTMLVideoElement | null): void {
  if (!video) return
  if (video.paused) {
    void video.play().catch(() => undefined)
    return
  }
  video.pause()
}

type FullscreenCapableVideo = HTMLVideoElement & {
  webkitRequestFullscreen?: () => Promise<void> | void
  msRequestFullscreen?: () => Promise<void> | void
}

/** 安全触发浏览器原生全屏，兼容常见旧版 WebKit/MS 前缀实现。 */
function requestVideoFullscreen(video: HTMLVideoElement | null): void {
  if (!video) {
    message.warning('当前视频暂不可全屏播放')
    return
  }
  const target = video as FullscreenCapableVideo
  const request = target.requestFullscreen ?? target.webkitRequestFullscreen ?? target.msRequestFullscreen
  if (!request) {
    message.warning('当前浏览器不支持全屏播放')
    return
  }
  void request.call(target)
}

/**
 * 展示当前镜头已生成的视频结果，改为小方块网格（参考分镜工作室主体展示）。
 * 数据来自任务链接（视频 ↔ 镜头关联），并用 shot.generated_video_file_id 兜底，
 * 避免该字段指向的视频因链接数据缺失而在列表中消失。
 */
export function ShotVideoResultsTab({ shot, selectedFileId, onSelectVideo, onDefaultSelectVideo }: ShotVideoResultsTabProps) {
  const [videos, setVideos] = useState<GeneratedVideoItem[]>([])
  const [loading, setLoading] = useState(false)
  const videoRefs = useRef<Record<string, HTMLVideoElement | null>>({})

  const shotId = shot?.id ?? null
  const currentFileId = shot?.generated_video_file_id?.trim() || ''

  useEffect(() => {
    if (!shotId) {
      setVideos([])
      return
    }
    let canceled = false
    setLoading(true)
    void (async () => {
      try {
        const links = await listTaskLinksNormalized({
          resourceType: 'video',
          relationType: 'video',
          relationEntityId: shotId,
          order: 'updated_at',
          isDesc: true,
          page: 1,
          pageSize: 100,
        })
        if (canceled) return
        const seen = new Set<string>()
        const list = links
          .filter((link) => Boolean(link.file_id))
          .map((link) => ({
            linkId: link.id,
            fileId: String(link.file_id),
            url: buildFileDownloadUrl(String(link.file_id)) ?? '',
          }))
          .filter((video) => Boolean(video.url))
          .filter((video) => {
            if (seen.has(video.fileId)) return false
            seen.add(video.fileId)
            return true
          })
        if (currentFileId && !list.some((video) => video.fileId === currentFileId)) {
          const currentUrl = buildFileDownloadUrl(currentFileId) ?? ''
          if (currentUrl) list.unshift({ linkId: -1, fileId: currentFileId, url: currentUrl })
        }
        setVideos(list)
        if (list.length > 0 && !selectedFileId) {
          onDefaultSelectVideo?.(list[0].fileId)
        }
      } catch {
        if (!canceled) setVideos([])
      } finally {
        if (!canceled) setLoading(false)
      }
    })()
    return () => {
      canceled = true
    }
    // selectedFileId 只用于判断“是否需要默认选中”，不需要在其变化时重新拉取列表。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shotId, currentFileId])

  const isEmpty = !shotId || (!loading && videos.length === 0)

  return (
    <Card
      className="flex h-full flex-col"
      title={
        <div className="flex items-center gap-2">
          <VideoCameraOutlined />
          <span>视频结果</span>
        </div>
      }
      bodyStyle={{ padding: 16, flex: 1, minHeight: 0, overflowY: 'auto' }}
    >
      {isEmpty ? (
        <Empty description={shotId ? '暂无视频，请在右侧配置生成参数后发起生成' : '请先选择一个镜头'} />
      ) : (
        <div className="grid grid-cols-2 xl:grid-cols-3 gap-4">
          {videos.map((item, idx) => {
            const isCurrent = currentFileId === item.fileId
            const isSelected = selectedFileId === item.fileId
            return (
              <div
                key={`${item.linkId}-${item.fileId}`}
                role="button"
                tabIndex={0}
                onClick={() => onSelectVideo?.(item.fileId)}
                className={`relative cursor-pointer rounded-xl border p-3 bg-white transition hover:border-blue-300 hover:shadow-lg ${
                  isSelected ? 'border-emerald-400 ring-2 ring-emerald-200' : 'border-gray-200'
                }`}
              >
                {isCurrent ? (
                  <span className="absolute right-2 top-2 z-10 rounded-md bg-gray-500/80 px-1.5 py-0.5 text-[10px] font-medium text-white">
                    当前使用
                  </span>
                ) : null}
                <div className="aspect-video overflow-hidden rounded-lg border border-gray-900 bg-black">
                  <video
                    ref={(node) => {
                      videoRefs.current[item.fileId] = node
                    }}
                    src={item.url}
                    className="h-full w-full cursor-pointer object-contain"
                    preload="metadata"
                    muted
                    playsInline
                    onClick={(event) => {
                      event.stopPropagation()
                      toggleVideoPlayback(event.currentTarget)
                    }}
                  />
                </div>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-700">视频 {idx + 1}</div>
                    <div className="truncate text-xs text-gray-400">{item.fileId}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1" onClick={(event) => event.stopPropagation()}>
                    <Tooltip title="全屏播放">
                      <Button
                        size="small"
                        icon={<FullscreenOutlined />}
                        onClick={() => requestVideoFullscreen(videoRefs.current[item.fileId] ?? null)}
                      />
                    </Tooltip>
                    <Tooltip title="下载视频">
                      <Button
                        size="small"
                        icon={<DownloadOutlined />}
                        onClick={() => window.open(item.url, '_blank', 'noopener,noreferrer')}
                      />
                    </Tooltip>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
