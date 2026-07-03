import type { ReactNode } from 'react'
import {
  EditOutlined,
  FileSearchOutlined,
  ScissorOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import type { Chapter } from './hooks/useProjectData'

export type ChapterPreparationState = {
  key: 'edit_raw' | 'extract_shots' | 'prepare_shots' | 'shoot'
  text: string
  color: string
  hint: string
  primaryAction: string
  primaryIcon: ReactNode
}

export function getChapterPreparationState(chapter: Chapter): ChapterPreparationState {
  const hasRawText = !!chapter.rawText?.trim()
  const hasShots = (chapter.storyboardCount ?? 0) > 0
  if (!hasRawText) {
    return {
      key: 'edit_raw',
      text: '待录入原文',
      color: 'default',
      hint: '先补章节原文，再进入分镜流程',
      primaryAction: '编辑原文',
      primaryIcon: <EditOutlined />,
    }
  }
  if (!hasShots) {
    return {
      key: 'extract_shots',
      text: '待提取分镜',
      color: 'gold',
      hint: '已有章节原文，下一步建议提取分镜并自动准备资产与对白',
      primaryAction: '提取分镜并自动准备',
      primaryIcon: <ScissorOutlined />,
    }
  }
  if (chapter.status === 'shooting' || chapter.status === 'done') {
    return {
      key: 'shoot',
      text: '可生成视频',
      color: 'green',
      hint: '当前章节已有可继续生成的视频分镜',
      primaryAction: '进入分镜',
      primaryIcon: <VideoCameraOutlined />,
    }
  }
  return {
    key: 'prepare_shots',
    text: '待确认分镜',
    color: 'blue',
    hint: '已有分镜，建议进入分镜列表处理待确认镜头',
    primaryAction: '进入分镜',
    primaryIcon: <FileSearchOutlined />,
  }
}
