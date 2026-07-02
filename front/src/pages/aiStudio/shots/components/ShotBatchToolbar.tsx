import { Button, Dropdown, Space } from 'antd'
import type { MenuProps } from 'antd'
import {
  DownloadOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from '@ant-design/icons'

type ShotBatchToolbarProps = {
  selectedCount: number
  generating?: boolean
  downloading?: boolean
  diagnosticLoading?: boolean
  disabled?: boolean
  maintenanceMenuItems: MenuProps['items']
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
  generating = false,
  downloading = false,
  diagnosticLoading = false,
  disabled = false,
  maintenanceMenuItems,
  onBatchGenerate,
  onBatchDownload,
  onBatchDiagnose,
  onClearSelection,
}: ShotBatchToolbarProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <Space size="small" wrap>
        <span className="text-xs text-slate-500">已选 {selectedCount} 条</span>
        <Button
          size="small"
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={generating}
          disabled={disabled}
          onClick={onBatchGenerate}
        >
          批量生成
        </Button>
        <Button
          size="small"
          icon={<DownloadOutlined />}
          loading={downloading}
          disabled={disabled}
          onClick={onBatchDownload}
        >
          批量下载
        </Button>
        <Button
          size="small"
          icon={<ToolOutlined />}
          loading={diagnosticLoading}
          disabled={disabled}
          onClick={onBatchDiagnose}
        >
          批量诊断
        </Button>
        <Dropdown menu={{ items: maintenanceMenuItems }} trigger={['click']} disabled={disabled}>
          <Button size="small" icon={<SettingOutlined />} disabled={disabled}>
            更多维护
          </Button>
        </Dropdown>
        <Button size="small" type="text" disabled={disabled} onClick={onClearSelection}>
          清空选择
        </Button>
      </Space>
    </div>
  )
}
