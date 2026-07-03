import { Button, Dropdown, Space } from 'antd'
import type { MenuProps } from 'antd'
import {
  ReloadOutlined,
  DownloadOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from '@ant-design/icons'

type ShotBatchToolbarProps = {
  selectedCount: number
  extracting?: boolean
  generating?: boolean
  downloading?: boolean
  diagnosticLoading?: boolean
  disabled?: boolean
  maintenanceMenuItems: MenuProps['items']
  extractLabel?: string
  generateLabel?: string
  downloadLabel?: string
  diagnoseLabel?: string
  moreLabel?: string
  clearLabel?: string
  onBatchExtract?: () => void
  onBatchGenerate: () => void
  onBatchDownload: () => void
  onBatchDiagnose: () => void
  onClearSelection: () => void
}

/**
 * 章节分镜列表的批量工具栏，承载跨镜头批量动作并避免把用户带回旧工作室入口。
 */
export function ShotBatchToolbar({
  selectedCount,
  extracting = false,
  generating = false,
  downloading = false,
  diagnosticLoading = false,
  disabled = false,
  maintenanceMenuItems,
  extractLabel = '批量提取',
  generateLabel = '批量生成',
  downloadLabel = '批量下载',
  diagnoseLabel = '批量诊断',
  moreLabel = '更多维护',
  clearLabel = '清空选择',
  onBatchExtract,
  onBatchGenerate,
  onBatchDownload,
  onBatchDiagnose,
  onClearSelection,
}: ShotBatchToolbarProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <Space size="small" wrap>
        <span className="text-xs text-slate-500">已选 {selectedCount} 条</span>
        {onBatchExtract ? (
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={extracting}
            disabled={disabled}
            onClick={onBatchExtract}
          >
            {extractLabel}
          </Button>
        ) : null}
        <Button
          size="small"
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={generating}
          disabled={disabled}
          onClick={onBatchGenerate}
        >
          {generateLabel}
        </Button>
        <Button
          size="small"
          icon={<DownloadOutlined />}
          loading={downloading}
          disabled={disabled}
          onClick={onBatchDownload}
        >
          {downloadLabel}
        </Button>
        <Button
          size="small"
          icon={<ToolOutlined />}
          loading={diagnosticLoading}
          disabled={disabled}
          onClick={onBatchDiagnose}
        >
          {diagnoseLabel}
        </Button>
        <Dropdown menu={{ items: maintenanceMenuItems }} trigger={['click']} disabled={disabled}>
          <Button size="small" icon={<SettingOutlined />} disabled={disabled}>
            {moreLabel}
          </Button>
        </Dropdown>
        <Button size="small" type="text" disabled={disabled} onClick={onClearSelection}>
          {clearLabel}
        </Button>
      </Space>
    </div>
  )
}
