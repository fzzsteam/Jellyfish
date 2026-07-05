import { useEffect, useMemo, useState } from 'react'
import { Button, Image, Input, Modal, Space, Spin, Tag, Tooltip } from 'antd'
import { HolderOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { DragDropContext, Draggable, Droppable, type DroppableProps, type DropResult } from 'react-beautiful-dnd'
import type { FrameGuidanceDecisionRead, PointsQuoteResponse, ShotFrameType, ShotFramePromptMappingRead, ShotLinkedAssetItem } from '../../../../services/generated'
import type { GenerationDraftState } from '../../hooks/useGenerationDraft'
import { PointsCostButton } from '../../../../components/points/PointsCostButton'
import { buildFileDownloadUrl } from '../../assets/utils'

export type KeyframeReferenceOption = ShotLinkedAssetItem & { kind: 'scene' | 'actor' | 'prop' | 'costume' }

function reorder<T>(list: T[], startIndex: number, endIndex: number): T[] {
  const result = list.slice()
  const [removed] = result.splice(startIndex, 1)
  result.splice(endIndex, 0, removed)
  return result
}

function readContextText(context: Record<string, unknown> | null, key: string): string {
  if (!context) return ''
  const value = context[key]
  return typeof value === 'string' ? value.trim() : ''
}

function stripDirectiveLevelPrefix(item: string): string {
  const text = item.trim()
  if (text.startsWith('必须：')) return text.slice(3).trim()
  if (text.startsWith('优先：')) return text.slice(3).trim()
  return text
}

function parseDirectorCommandSummary(summary: string): Array<{ level: 'must' | 'prefer'; text: string }> {
  return summary
    .split('；')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      if (item.startsWith('必须：')) return { level: 'must' as const, text: item.slice(3).trim() }
      if (item.startsWith('优先：')) return { level: 'prefer' as const, text: item.slice(3).trim() }
      return { level: 'prefer' as const, text: item }
    })
}

function buildGuidanceSummary(items: string[]): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  items
    .flatMap((item) => item.split('；'))
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((item) => {
      if (seen.has(item)) return
      seen.add(item)
      result.push(item)
    })
  return result
}

function buildGuidanceLevelSummary(
  parsedDirectorCommands: Array<{ level: 'must' | 'prefer'; text: string }>,
  guidanceSummary: string[],
): { must: number; prefer: number; normal: number } {
  const must = parsedDirectorCommands.filter((item) => item.level === 'must').length
  const prefer = parsedDirectorCommands.filter((item) => item.level === 'prefer').length
  const parsedTexts = new Set(parsedDirectorCommands.map((item) => item.text.trim()).filter(Boolean))
  const normal = guidanceSummary
    .map((item) => stripDirectiveLevelPrefix(item))
    .filter((item) => item && !parsedTexts.has(item)).length
  return { must, prefer, normal }
}

function buildActionBeatPhaseTags(summary: string): Array<{ text: string; phaseLabel: string }> {
  return summary
    .split('；')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const matched = item.match(/^\d+\.\s*(触发|峰值|收束)\s*·\s*(.+)$/)
      if (!matched) return { phaseLabel: '阶段', text: item }
      return { phaseLabel: matched[1], text: matched[2].trim() }
    })
}

function mapDraftStateToRenderState(state: GenerationDraftState): 'idle' | 'stale' | 'syncing' | 'clean' | 'error' {
  if (state === 'derived' || state === 'submitted') return 'clean'
  if (state === 'deriving' || state === 'submitting') return 'syncing'
  if (state === 'draft_changed' || state === 'context_changed') return 'stale'
  if (state === 'error') return 'error'
  return 'idle'
}

function getRenderStatusMeta(state: GenerationDraftState) {
  const renderState = mapDraftStateToRenderState(state)
  if (renderState === 'clean') {
    return { color: 'green' as const, label: '已同步', description: '当前最终提示词已与基础提示词和参考图顺序保持一致。' }
  }
  if (renderState === 'syncing') {
    return { color: 'blue' as const, label: '同步中', description: '正在根据当前基础提示词和参考图顺序更新最终提示词…' }
  }
  if (renderState === 'error') {
    return { color: 'red' as const, label: '同步失败', description: '自动更新失败，请点击"重新同步"重试。' }
  }
  if (renderState === 'idle') {
    return { color: 'default' as const, label: '待生成', description: '请先输入基础提示词，系统会自动生成最终提示词。' }
  }
  return { color: 'gold' as const, label: '待同步', description: '基础提示词或参考图顺序已变化，最终提示词正在等待更新。' }
}

const KIND_LABEL: Record<KeyframeReferenceOption['kind'], string> = { scene: '场景', actor: '角色', prop: '道具', costume: '服装' }

/**
 * react-beautiful-dnd 在 React 18 StrictMode 开发态会因为重复挂载导致 Droppable 注册失效。
 * 延迟一帧渲染 Droppable，可保持入口 StrictMode 不变，同时让拖拽区域正常注册。
 */
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

type ShotKeyframeGenerateModalProps = {
  open: boolean
  frameType: ShotFrameType | null
  frameLabel: string
  loading: boolean
  submitting: boolean
  prompt: string
  onPromptChange: (value: string) => void
  imageQuote: PointsQuoteResponse | null
  imageQuoteLoading: boolean
  imageQuoteError: string | null
  referenceOptions: KeyframeReferenceOption[]
  onAddReferenceFromLibrary: () => void
  onReplaceReferenceFromLibrary: (fileId: string) => void
  selectedFileIds: string[]
  onChangeSelectedFileIds: (fileIds: string[]) => void
  onClose: () => void
  onSubmit: () => void
  // AI 生成基础提示词
  basePromptQuote: PointsQuoteResponse | null
  basePromptQuoteLoading: boolean
  basePromptQuoteError: string | null
  aiGenerating: boolean
  onRegenerateBasePrompt: () => void
  // 最终提示词渲染
  renderState: GenerationDraftState
  renderedPrompt: string
  onResync: () => void
  mappings: ShotFramePromptMappingRead[]
  selectedGuidance: string[]
  droppedGuidance: string[]
  selectedGuidanceDetails: FrameGuidanceDecisionRead[]
  droppedGuidanceDetails: FrameGuidanceDecisionRead[]
  debugContext: Record<string, unknown> | null
  qualityChecks: { passed: boolean; issues: string[] } | null
}

/**
 * 关键帧生成弹窗：移植自分镜工作室"首帧/关键帧/尾帧图片生成提示词预览"弹窗的完整能力
 * （参考图有序展示、AI 生成基础提示词、质量校验、guidance 摘要、最终提示词渲染），
 * 并在此基础上新增分镜工作室原版没有的能力——参考图可自由从项目资产库新增/替换，
 * 且仅作为本次生成的临时参考图，不写入镜头资产关联关系。
 */
export function ShotKeyframeGenerateModal({
  open,
  frameType: _frameType,
  frameLabel,
  loading,
  submitting,
  prompt,
  onPromptChange,
  imageQuote,
  imageQuoteLoading,
  imageQuoteError,
  referenceOptions,
  onAddReferenceFromLibrary,
  onReplaceReferenceFromLibrary,
  selectedFileIds,
  onChangeSelectedFileIds,
  onClose,
  onSubmit,
  basePromptQuote,
  basePromptQuoteLoading,
  basePromptQuoteError,
  aiGenerating,
  onRegenerateBasePrompt,
  renderState,
  renderedPrompt,
  onResync,
  mappings,
  selectedGuidance,
  droppedGuidance,
  selectedGuidanceDetails,
  droppedGuidanceDetails,
  debugContext,
  qualityChecks,
}: ShotKeyframeGenerateModalProps) {
  const [debugCollapsed, setDebugCollapsed] = useState(true)
  const [directiveCollapsed, setDirectiveCollapsed] = useState(true)
  const [decisionCollapsed, setDecisionCollapsed] = useState(true)
  const [previewFileId, setPreviewFileId] = useState<string | null>(null)

  const nameByFileId = useMemo(() => {
    const map = new Map<string, string>()
    referenceOptions.forEach((option) => {
      if (option.file_id) map.set(option.file_id, option.name)
    })
    return map
  }, [referenceOptions])

  const removeFileId = (fileId: string) => {
    onChangeSelectedFileIds(selectedFileIds.filter((id) => id !== fileId))
  }

  // 拖拽结束后只更新参考图顺序；图1/图2映射由后续 render-prompt 自动同步。
  const handleReferenceDragEnd = (result: DropResult) => {
    if (!result.destination) return
    if (result.destination.index === result.source.index) return
    onChangeSelectedFileIds(reorder(selectedFileIds, result.source.index, result.destination.index))
  }

  const hasBasePrompt = prompt.trim().length > 0
  const renderStatusMeta = getRenderStatusMeta(renderState)
  const debugVisualStyle = readContextText(debugContext, 'visual_style')
  const debugStyle = readContextText(debugContext, 'style')
  const debugShotDescription = readContextText(debugContext, 'shot_description')
  const debugDialogSummary = readContextText(debugContext, 'dialog_summary')
  const debugPreviousShotTitle = readContextText(debugContext, 'previous_shot_title')
  const debugPreviousShotEndState = readContextText(debugContext, 'previous_shot_end_state')
  const debugNextShotTitle = readContextText(debugContext, 'next_shot_title')
  const debugNextShotStartGoal = readContextText(debugContext, 'next_shot_start_goal')
  const debugContinuityGuidance = readContextText(debugContext, 'continuity_guidance')
  const debugCompositionAnchor = readContextText(debugContext, 'composition_anchor')
  const debugScreenDirectionGuidance = readContextText(debugContext, 'screen_direction_guidance')
  const debugFrameSpecificGuidance = readContextText(debugContext, 'frame_specific_guidance')
  const debugDirectorCommandSummary = readContextText(debugContext, 'director_command_summary')
  const debugActionBeatPhases = readContextText(debugContext, 'action_beat_phases')
  const actionBeatPhaseTags = buildActionBeatPhaseTags(debugActionBeatPhases)
  const parsedDirectorCommandSummary = parseDirectorCommandSummary(debugDirectorCommandSummary)
  const guidanceSummary = buildGuidanceSummary([
    debugDirectorCommandSummary,
    debugFrameSpecificGuidance,
    debugContinuityGuidance,
    debugCompositionAnchor,
    debugScreenDirectionGuidance,
  ])
  const guidanceLevelSummary = buildGuidanceLevelSummary(parsedDirectorCommandSummary, guidanceSummary)
  const hasDebugContext = Boolean(
    debugVisualStyle || debugStyle || debugShotDescription || debugDialogSummary ||
    debugPreviousShotTitle || debugPreviousShotEndState || debugNextShotTitle || debugNextShotStartGoal ||
    debugContinuityGuidance || debugCompositionAnchor || debugScreenDirectionGuidance || debugFrameSpecificGuidance ||
    debugDirectorCommandSummary || debugActionBeatPhases,
  )
  const hasQualityChecks = qualityChecks !== null
  const visibleSelectedGuidanceDetails = decisionCollapsed ? selectedGuidanceDetails.slice(0, 2) : selectedGuidanceDetails
  const visibleDroppedGuidanceDetails = decisionCollapsed ? droppedGuidanceDetails.slice(0, 1) : droppedGuidanceDetails

  return (
    <Modal
      title={`生成${frameLabel}`}
      open={open}
      onCancel={() => {
        if (aiGenerating) return
        onClose()
      }}
      footer={(
        <Space>
          <Button disabled={aiGenerating} onClick={onClose}>取消</Button>
          <PointsCostButton
            type="primary"
            loading={submitting}
            disabled={!hasBasePrompt}
            quote={imageQuote}
            quoteLoading={imageQuoteLoading}
            quoteError={imageQuoteError}
            onClick={onSubmit}
          >
            生成
          </PointsCostButton>
        </Space>
      )}
      width={900}
      destroyOnClose
    >
      {loading ? (
        <div className="py-10 text-center"><Spin /></div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="mb-2 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-slate-900">参考图</div>
                <div className="mt-1 text-xs text-slate-500">图片顺序决定最终提示词里的图序映射；拖拽图片主体可调整顺序，也可从项目资产库添加或替换。</div>
              </div>
              <Space size="small">
                <Tag color="gold">顺序影响图序</Tag>
                <Button size="small" icon={<PlusOutlined />} onClick={onAddReferenceFromLibrary}>
                  添加资产
                </Button>
              </Space>
            </div>
            {selectedFileIds.length === 0 ? (
              <div className="text-xs text-gray-400">暂无参考图，可点击“添加资产”从资产库新增</div>
            ) : (
              <DragDropContext onDragEnd={handleReferenceDragEnd}>
                <StrictModeDroppable droppableId="keyframe-reference-files" direction="horizontal">
                  {(provided) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      className="flex gap-3 overflow-x-auto pb-2"
                    >
                      {selectedFileIds.map((fid, index) => {
                        const option = referenceOptions.find((item) => item.file_id === fid)
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
                                  <Tag color="blue" className="!m-0">{`图${index + 1}`}</Tag>
                                  <span
                                    className="inline-flex h-6 w-6 items-center justify-center rounded text-slate-400"
                                    aria-hidden="true"
                                  >
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
                                      alt={nameByFileId.get(fid) ?? `参考图${index + 1}`}
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
                                <div className="mt-2 flex items-center gap-1">
                                  {option?.kind ? <Tag className="!m-0" color="default">{KIND_LABEL[option.kind]}</Tag> : null}
                                  <div className="min-w-0 flex-1 truncate text-[11px] text-gray-700">{nameByFileId.get(fid) ?? fid}</div>
                                </div>
                                <div className="mt-2 flex gap-1">
                                  <Button size="small" className="flex-1" onClick={() => onReplaceReferenceFromLibrary(fid)}>替换</Button>
                                  <Button size="small" danger onClick={() => removeFileId(fid)}>移除</Button>
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

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="mb-2 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-slate-900">基础提示词</div>
                <div className="mt-1 text-xs text-slate-500">描述画面内容本身，不含图片映射说明；AI 生成会继承项目风格并参考已确认的角色/场景/道具/服装设定。</div>
              </div>
              <Space size="small">
                <Tag color={hasBasePrompt ? 'blue' : 'default'}>{hasBasePrompt ? '可编辑' : '未生成'}</Tag>
                <PointsCostButton
                  size="small"
                  type={hasBasePrompt ? 'default' : 'primary'}
                  loading={aiGenerating}
                  quote={basePromptQuote}
                  quoteLoading={basePromptQuoteLoading}
                  quoteError={basePromptQuoteError}
                  onClick={onRegenerateBasePrompt}
                >
                  AI生成
                </PointsCostButton>
              </Space>
            </div>
            {!hasBasePrompt ? (
              <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                当前还没有基础提示词。你可以先让 AI 生成一版，再按需修改；也可以直接手动输入。
              </div>
            ) : null}
            {hasQualityChecks ? (
              <div className={`mb-3 rounded-lg border px-3 py-2 text-xs ${qualityChecks?.passed ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'}`}>
                <Tag color={qualityChecks?.passed ? 'green' : 'gold'}>{qualityChecks?.passed ? '质量校验通过' : '已触发自动修正'}</Tag>
                <span className="ml-2">{qualityChecks?.passed ? '本次 AI 生成已通过基础质量校验。' : '本次 AI 生成触发过自动修正，系统已尽量清理不符合基础提示词要求的内容。'}</span>
              </div>
            ) : null}
            <Input.TextArea
              rows={5}
              value={prompt}
              onChange={(e) => onPromptChange(e.target.value)}
              placeholder="请输入基础提示词，例如人物动作、场景氛围、镜头视角等…"
              disabled={aiGenerating}
            />
            {guidanceSummary.length > 0 || debugDirectorCommandSummary ? (
              <div className="mt-3 rounded-lg border border-sky-200 bg-sky-50 px-3 py-3 text-xs text-sky-800">
                <div className="flex items-start justify-between gap-3">
                  <div className="font-medium">基础提示词生成依据</div>
                  <Button size="small" type="text" onClick={() => setDirectiveCollapsed((prev) => !prev)}>
                    {directiveCollapsed ? '展开细节' : '收起细节'}
                  </Button>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Tag color="red">{`必须 ${guidanceLevelSummary.must}`}</Tag>
                  <Tag color="blue">{`优先 ${guidanceLevelSummary.prefer}`}</Tag>
                  <Tag>{`普通 ${guidanceLevelSummary.normal}`}</Tag>
                  {actionBeatPhaseTags.length > 0 ? <Tag color="purple">{`动作阶段 ${actionBeatPhaseTags.length}`}</Tag> : null}
                </div>
                {!directiveCollapsed ? (
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {debugDirectorCommandSummary ? (
                      <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-3 text-xs text-indigo-800">
                        <div className="font-medium">高优先级导演指令</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {parsedDirectorCommandSummary.map((item, index) => (
                            <Tag key={`${item.level}:${index}`} color={item.level === 'must' ? 'red' : 'blue'}>
                              {item.level === 'must' ? '必须' : '优先'} · {item.text}
                            </Tag>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {actionBeatPhaseTags.length > 0 ? (
                      <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
                        <div className="font-medium text-slate-800">动作节拍阶段</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {actionBeatPhaseTags.map((item, index) => (
                            <Tag key={`${item.phaseLabel}:${index}`} color={item.phaseLabel === '触发' ? 'gold' : item.phaseLabel === '峰值' ? 'blue' : 'green'}>
                              {item.phaseLabel} · {item.text}
                            </Tag>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
            {hasDebugContext ? (
              <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-600">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-slate-700">最近一次 AI 生成上下文</div>
                  <Button size="small" type="text" onClick={() => setDebugCollapsed((prev) => !prev)}>
                    {debugCollapsed ? '展开细节' : '收起细节'}
                  </Button>
                </div>
                {!debugCollapsed ? (
                  <div className="mt-2 grid gap-2 md:grid-cols-2">
                    {[debugVisualStyle, debugStyle].filter(Boolean).length > 0 ? (
                      <div><div className="text-slate-500">项目风格</div><div className="mt-1 text-slate-700">{[debugVisualStyle, debugStyle].filter(Boolean).join(' / ')}</div></div>
                    ) : null}
                    {debugShotDescription ? <div className="md:col-span-2"><div className="text-slate-500">镜头补充描述</div><div className="mt-1 whitespace-pre-wrap text-slate-700">{debugShotDescription}</div></div> : null}
                    {debugDialogSummary ? <div className="md:col-span-2"><div className="text-slate-500">对白摘要</div><div className="mt-1 whitespace-pre-wrap text-slate-700">{debugDialogSummary}</div></div> : null}
                    {debugPreviousShotTitle || debugPreviousShotEndState ? (
                      <div className="md:col-span-2 rounded-lg border border-slate-200 bg-white px-3 py-3">
                        <div className="text-slate-500">上一镜头承接</div>
                        <div className="mt-1 space-y-1 text-slate-700">
                          {debugPreviousShotTitle ? <div>标题：{debugPreviousShotTitle}</div> : null}
                          {debugPreviousShotEndState ? <div className="whitespace-pre-wrap">结尾状态：{debugPreviousShotEndState}</div> : null}
                        </div>
                      </div>
                    ) : null}
                    {debugNextShotTitle || debugNextShotStartGoal ? (
                      <div className="md:col-span-2 rounded-lg border border-slate-200 bg-white px-3 py-3">
                        <div className="text-slate-500">下一镜头衔接</div>
                        <div className="mt-1 space-y-1 text-slate-700">
                          {debugNextShotTitle ? <div>标题：{debugNextShotTitle}</div> : null}
                          {debugNextShotStartGoal ? <div className="whitespace-pre-wrap">起始目标：{debugNextShotStartGoal}</div> : null}
                        </div>
                      </div>
                    ) : null}
                    {debugContinuityGuidance ? <div className="md:col-span-2"><div className="text-slate-500">连续性建议</div><div className="mt-1 whitespace-pre-wrap text-slate-700">{debugContinuityGuidance}</div></div> : null}
                    {debugCompositionAnchor ? <div className="md:col-span-2"><div className="text-slate-500">构图与空间锚点</div><div className="mt-1 whitespace-pre-wrap text-slate-700">{debugCompositionAnchor}</div></div> : null}
                    {debugScreenDirectionGuidance ? <div className="md:col-span-2"><div className="text-slate-500">朝向与视线建议</div><div className="mt-1 whitespace-pre-wrap text-slate-700">{debugScreenDirectionGuidance}</div></div> : null}
                    {debugFrameSpecificGuidance ? <div className="md:col-span-2"><div className="text-slate-500">当前帧专项建议</div><div className="mt-1 whitespace-pre-wrap text-slate-700">{debugFrameSpecificGuidance}</div></div> : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-slate-900">最终生成提示词</div>
                <div className="mt-1 text-xs text-slate-500">系统根据当前基础提示词和参考图顺序自动生成，提交生成时使用这里的结果。</div>
              </div>
              <Space size="small">
                <Tag>只读</Tag>
                <Button size="small" onClick={onResync} disabled={!hasBasePrompt}>重新同步</Button>
                <Button
                  size="small"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(renderedPrompt || '')
                    } catch {
                      // ignore clipboard failure，不阻塞主流程
                    }
                  }}
                  disabled={!renderedPrompt.trim()}
                >
                  复制
                </Button>
              </Space>
            </div>
            <div className={`mb-3 rounded-lg border px-3 py-2 text-sm ${
              renderStatusMeta.color === 'green' ? 'border-green-200 bg-green-50 text-green-700'
                : renderStatusMeta.color === 'blue' ? 'border-blue-200 bg-blue-50 text-blue-700'
                : renderStatusMeta.color === 'red' ? 'border-red-200 bg-red-50 text-red-700'
                : renderStatusMeta.color === 'gold' ? 'border-amber-200 bg-amber-50 text-amber-700'
                : 'border-slate-200 bg-white text-slate-600'
            }`}>
              <Tag color={renderStatusMeta.color}>{renderStatusMeta.label}</Tag>
              <span className="ml-2">{renderStatusMeta.description}</span>
            </div>
            {mappings.length > 0 ? (
              <div className="mb-2 flex flex-wrap gap-2">
                {mappings.map((mapping) => (
                  <Tag key={`${mapping.token}:${mapping.file_id}`}>{`${mapping.token} = ${mapping.name}`}</Tag>
                ))}
              </div>
            ) : null}
            {selectedGuidance.length > 0 || droppedGuidance.length > 0 ? (
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-slate-900">最终提示词收敛结果</div>
                  <Space size="small">
                    <Tag color="green">{`保留 ${selectedGuidance.length}`}</Tag>
                    <Tag color="gold">{`压缩 ${droppedGuidance.length}`}</Tag>
                    <Button size="small" type="text" onClick={() => setDecisionCollapsed((prev) => !prev)}>
                      {decisionCollapsed ? '查看取舍' : '收起取舍'}
                    </Button>
                  </Space>
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-xs text-emerald-800">
                    <div className="font-medium">实际保留</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {visibleSelectedGuidanceDetails.map((item) => (
                        <Tooltip key={`selected:${item.text}`} title={item.reason}>
                          <Tag color="green" className="max-w-full whitespace-normal break-words leading-5">{item.text}</Tag>
                        </Tooltip>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-600">
                    <div className="font-medium">已压缩</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {visibleDroppedGuidanceDetails.map((item) => (
                        <Tooltip key={`dropped:${item.text}`} title={item.reason}>
                          <Tag className="max-w-full whitespace-normal break-words leading-5">{item.text}</Tag>
                        </Tooltip>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </Modal>
  )
}
