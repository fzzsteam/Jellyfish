import { useMemo } from 'react'
import { Button, Checkbox, Input, Modal, Spin } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons'
import type { ShotFrameType, ShotLinkedAssetItem } from '../../../../services/generated'

export type KeyframeReferenceOption = ShotLinkedAssetItem & { kind: 'scene' | 'actor' | 'prop' | 'costume' }

type ShotKeyframeGenerateModalProps = {
  open: boolean
  frameType: ShotFrameType | null
  frameLabel: string
  loading: boolean
  submitting: boolean
  prompt: string
  onPromptChange: (value: string) => void
  quoteText: string | null
  referenceOptions: KeyframeReferenceOption[]
  selectedFileIds: string[]
  onChangeSelectedFileIds: (fileIds: string[]) => void
  onClose: () => void
  onSubmit: () => void
}

/**
 * 关键帧生成弹窗：默认列出当前镜头已关联资产作为参考图（等价于旧页自动收集），
 * 可勾选/取消，并可用上移下移按钮调整顺序；编辑提示词后提交生成任务。
 */
export function ShotKeyframeGenerateModal({
  open,
  // frameType 目前仅用于类型契约（调用方传入以备将来按帧类型定制文案/校验），当前渲染只依赖 frameLabel。
  frameType: _frameType,
  frameLabel,
  loading,
  submitting,
  prompt,
  onPromptChange,
  quoteText,
  referenceOptions,
  selectedFileIds,
  onChangeSelectedFileIds,
  onClose,
  onSubmit,
}: ShotKeyframeGenerateModalProps) {
  const optionsByKind = useMemo(() => {
    const groups: Record<string, KeyframeReferenceOption[]> = { scene: [], actor: [], prop: [], costume: [] }
    referenceOptions.forEach((option) => {
      groups[option.kind]?.push(option)
    })
    return groups
  }, [referenceOptions])

  const toggleFileId = (fileId: string, checked: boolean) => {
    if (checked) {
      if (selectedFileIds.includes(fileId)) return
      onChangeSelectedFileIds([...selectedFileIds, fileId])
    } else {
      onChangeSelectedFileIds(selectedFileIds.filter((id) => id !== fileId))
    }
  }

  const moveFileId = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= selectedFileIds.length) return
    const next = selectedFileIds.slice()
    const [item] = next.splice(index, 1)
    next.splice(target, 0, item)
    onChangeSelectedFileIds(next)
  }

  const kindLabel: Record<string, string> = { scene: '场景', actor: '角色', prop: '道具', costume: '服装' }

  return (
    <Modal
      title={`生成${frameLabel}`}
      open={open}
      onCancel={onClose}
      onOk={onSubmit}
      okButtonProps={{ loading: submitting, disabled: !prompt.trim() }}
      okText="提交生成"
      width={720}
      destroyOnClose
    >
      {loading ? (
        <div className="py-10 text-center">
          <Spin />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="space-y-1">
            <div className="text-xs text-slate-500">提示词</div>
            <Input.TextArea value={prompt} onChange={(e) => onPromptChange(e.target.value)} autoSize={{ minRows: 2, maxRows: 6 }} />
          </div>

          <div className="space-y-2">
            <div className="text-xs text-slate-500">参考图（默认取当前镜头已关联资产，可取消勾选或调整顺序）</div>
            {(['scene', 'actor', 'prop', 'costume'] as const).map((kind) =>
              optionsByKind[kind].length > 0 ? (
                <div key={kind} className="space-y-1">
                  <div className="text-[11px] font-medium text-slate-600">{kindLabel[kind]}</div>
                  <div className="flex flex-wrap gap-2">
                    {optionsByKind[kind].map((option) => (
                      <Checkbox
                        key={`${option.type}:${option.id}`}
                        checked={!!option.file_id && selectedFileIds.includes(option.file_id)}
                        disabled={!option.file_id}
                        onChange={(e) => option.file_id && toggleFileId(option.file_id, e.target.checked)}
                      >
                        {option.name}
                      </Checkbox>
                    ))}
                  </div>
                </div>
              ) : null,
            )}
          </div>

          {selectedFileIds.length > 0 ? (
            <div className="space-y-1">
              <div className="text-xs text-slate-500">已选参考图顺序（影响融图优先级）</div>
              <div className="space-y-1">
                {selectedFileIds.map((fileId, index) => {
                  const matched = referenceOptions.find((option) => option.file_id === fileId)
                  return (
                    <div key={fileId} className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-2 py-1 text-xs">
                      <span>{matched?.name ?? fileId}</span>
                      <div className="flex items-center gap-1">
                        <Button
                          size="small"
                          type="text"
                          icon={<ArrowUpOutlined />}
                          disabled={index === 0}
                          onClick={() => moveFileId(index, -1)}
                        />
                        <Button
                          size="small"
                          type="text"
                          icon={<ArrowDownOutlined />}
                          disabled={index === selectedFileIds.length - 1}
                          onClick={() => moveFileId(index, 1)}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : null}

          {quoteText ? <div className="text-xs text-slate-500">{quoteText}</div> : null}
        </div>
      )}
    </Modal>
  )
}
