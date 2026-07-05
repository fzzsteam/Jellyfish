/**
 * AssetReferencePanel — 资产编辑页的参考图管理区块
 *
 * 展示当前已选中的参考图（均来自其他资产），支持拖拽调整顺序、替换、移除、
 * 点击放大预览。参考图顺序会原样传给生成接口的 images 字段。
 */

import { useEffect, useState } from 'react'
import { Button, Image, Tag, Tooltip } from 'antd'
import { HolderOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { DragDropContext, Draggable, Droppable, type DroppableProps, type DropResult } from 'react-beautiful-dnd'
import { buildFileDownloadUrl } from '../utils'
import type { AssetReferenceKind, AssetReferenceOption } from './AssetReferencePickerDrawer'

const KIND_LABEL: Record<AssetReferenceKind, string> = {
  character: '角色',
  actor: '演员',
  scene: '场景',
  prop: '道具',
  costume: '服装',
}

function reorder<T>(list: T[], startIndex: number, endIndex: number): T[] {
  const result = list.slice()
  const [removed] = result.splice(startIndex, 1)
  result.splice(endIndex, 0, removed)
  return result
}

// react-beautiful-dnd 在 React 18 StrictMode 下首帧渲染会报错，延后一帧启用 Droppable 规避。
function StrictModeDroppable({ children, ...props }: DroppableProps) {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    const animation = requestAnimationFrame(() => setEnabled(true))
    return () => {
      cancelAnimationFrame(animation)
      setEnabled(false)
    }
  }, [])

  if (!enabled) return null
  return <Droppable {...props}>{children}</Droppable>
}

type AssetReferencePanelProps = {
  options: AssetReferenceOption[]
  selectedFileIds: string[]
  onChangeSelectedFileIds: (fileIds: string[]) => void
  onAddFromLibrary: () => void
  onReplaceFromLibrary: (fileId: string) => void
  disabled?: boolean
}

export function AssetReferencePanel({
  options,
  selectedFileIds,
  onChangeSelectedFileIds,
  onAddFromLibrary,
  onReplaceFromLibrary,
  disabled = false,
}: AssetReferencePanelProps) {
  const [previewFileId, setPreviewFileId] = useState<string | null>(null)

  const optionByFileId = new Map(options.map((option) => [option.file_id, option]))

  const removeFileId = (fileId: string) => {
    onChangeSelectedFileIds(selectedFileIds.filter((id) => id !== fileId))
  }

  const handleDragEnd = (result: DropResult) => {
    if (!result.destination) return
    if (result.destination.index === result.source.index) return
    onChangeSelectedFileIds(reorder(selectedFileIds, result.source.index, result.destination.index))
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-slate-900">参考图</div>
          <div className="mt-1 text-xs text-slate-500">从资产库选择其他资产的图片作为参考，多张参考图会一起融合生成。</div>
        </div>
        <Button size="small" icon={<PlusOutlined />} disabled={disabled} onClick={onAddFromLibrary}>
          添加参考图
        </Button>
      </div>
      {selectedFileIds.length === 0 ? (
        <div className="text-xs text-gray-400">暂无参考图，可点击"添加参考图"从资产库新增</div>
      ) : (
        <DragDropContext onDragEnd={handleDragEnd}>
          <StrictModeDroppable droppableId="asset-reference-files" direction="horizontal">
            {(provided) => (
              <div ref={provided.innerRef} {...provided.droppableProps} className="flex gap-3 overflow-x-auto pb-2">
                {selectedFileIds.map((fid, index) => {
                  const option = optionByFileId.get(fid)
                  return (
                    <Draggable key={fid} draggableId={fid} index={index}>
                      {(dragProvided, snapshot) => (
                        <div
                          ref={dragProvided.innerRef}
                          {...dragProvided.draggableProps}
                          className={[
                            'w-[132px] shrink-0 rounded-lg border bg-white p-2 shadow-sm transition-shadow',
                            snapshot.isDragging ? 'border-blue-400 shadow-md' : 'border-slate-200',
                          ].join(' ')}
                        >
                          <div className="mb-1 flex items-center justify-between gap-1">
                            {option ? <Tag className="!m-0" color="default">{KIND_LABEL[option.kind]}</Tag> : <span />}
                            <span className="inline-flex h-6 w-6 items-center justify-center rounded text-slate-400" aria-hidden="true">
                              <HolderOutlined />
                            </span>
                          </div>
                          <Tooltip title="按住图片拖拽调整顺序">
                            <div
                              {...dragProvided.dragHandleProps}
                              className="group relative h-[78px] w-[116px] cursor-grab overflow-hidden rounded-lg border border-slate-200 bg-slate-100 active:cursor-grabbing"
                            >
                              <img
                                src={buildFileDownloadUrl(fid)}
                                alt={option?.entityName ?? `参考图${index + 1}`}
                                className="h-full w-full select-none object-cover"
                                draggable={false}
                              />
                              <button
                                type="button"
                                className="absolute right-1 top-1 inline-flex h-6 w-6 items-center justify-center rounded bg-white/90 text-slate-600 shadow-sm transition hover:bg-white hover:text-blue-600"
                                aria-label="预览参考图"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  setPreviewFileId(fid)
                                }}
                              >
                                <SearchOutlined className="text-xs" />
                              </button>
                            </div>
                          </Tooltip>
                          <div className="mt-2 truncate text-[11px] text-gray-700">{option?.entityName ?? fid}</div>
                          <div className="mt-2 flex gap-1">
                            <Button size="small" className="flex-1" disabled={disabled} onClick={() => onReplaceFromLibrary(fid)}>
                              替换
                            </Button>
                            <Button size="small" danger disabled={disabled} onClick={() => removeFileId(fid)}>
                              移除
                            </Button>
                          </div>
                        </div>
                      )}
                    </Draggable>
                  )
                })}
                {provided.placeholder}
              </div>
            )}
          </StrictModeDroppable>
        </DragDropContext>
      )}
      <Image
        src={previewFileId ? buildFileDownloadUrl(previewFileId) : undefined}
        style={{ display: 'none' }}
        preview={{
          visible: !!previewFileId,
          src: previewFileId ? buildFileDownloadUrl(previewFileId) : undefined,
          onVisibleChange: (visible) => {
            if (!visible) setPreviewFileId(null)
          },
        }}
      />
    </div>
  )
}
