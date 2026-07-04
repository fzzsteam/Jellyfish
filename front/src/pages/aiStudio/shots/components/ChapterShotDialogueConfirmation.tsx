import { Button, Input, Spin, Tooltip } from 'antd'
import { DeleteOutlined, FireOutlined, PlusOutlined, SmileOutlined } from '@ant-design/icons'
import type {
  ShotDialogLineRead,
  ShotExtractionSummaryRead,
  ShotExtractedDialogueCandidateRead,
} from '../../../../services/generated'

function dialogTitle(speaker?: string | null, target?: string | null) {
  const s = (speaker ?? '').trim() || '未知'
  const t = (target ?? '').trim() || '未知'
  return `${s} → ${t}`
}

type ChapterShotDialogueConfirmationProps = {
  extraction: ShotExtractionSummaryRead
  savedDialogLines: ShotDialogLineRead[]
  extractedDialogLines: ShotExtractedDialogueCandidateRead[]
  batchDialogAdding: boolean
  dialogLoading: boolean
  dialogDeletingIds: Record<number, boolean>
  dialogAddingKeys: Record<string, boolean>
  onAcceptAll: () => void
  onIgnoreAll: () => void
  onDeleteSavedDialogLine: (lineId: number) => void
  onUpdateSavedDialogText: (lineId: number, text: string) => void
  onAddExtractedDialogLine: (line: ShotExtractedDialogueCandidateRead) => void
  onIgnoreExtractedDialogLine: (line: ShotExtractedDialogueCandidateRead) => void
  onUpdateExtractedDialogText: (candidateId: number, text: string) => void
  /** 新增一条本地草稿对白（尚未持久化），插入到已保存列表末尾 */
  onAddDraftDialogueLine: () => void
  /** 草稿行内容变化（说话人/对象/文本），非空文本时由父组件负责创建持久化记录 */
  draftDialogueLine: { speakerName: string; targetName: string; text: string } | null
  onUpdateDraftDialogueLine: (patch: Partial<{ speakerName: string; targetName: string; text: string }>) => void
  onBlurDraftDialogueLine: () => void
  draftDialogueSaving: boolean
}

export function ChapterShotDialogueConfirmation({
  extraction,
  savedDialogLines,
  extractedDialogLines,
  batchDialogAdding,
  dialogLoading,
  dialogDeletingIds,
  dialogAddingKeys,
  onAcceptAll,
  onIgnoreAll,
  onDeleteSavedDialogLine,
  onUpdateSavedDialogText,
  onAddExtractedDialogLine,
  onIgnoreExtractedDialogLine,
  onUpdateExtractedDialogText,
  onAddDraftDialogueLine,
  draftDialogueLine,
  onUpdateDraftDialogueLine,
  onBlurDraftDialogueLine,
  draftDialogueSaving,
}: ChapterShotDialogueConfirmationProps) {
  const pendingCount = extractedDialogLines.length
  const dialogueStatus = (() => {
    if (extraction.state === 'skipped') {
      return { text: '已跳过', tone: 'blue' as const }
    }
    if (extraction.state === 'not_extracted') {
      return { text: '未提取', tone: 'gold' as const }
    }
    if ((extraction.dialogue_candidate_total ?? 0) === 0 && extraction.state === 'extracted_empty') {
      return { text: '已提取无候选', tone: 'default' as const }
    }
    if (pendingCount > 0) {
      return { text: `待处理 ${pendingCount}`, tone: 'gold' as const }
    }
    return { text: '已完成', tone: 'green' as const }
  })()
  const emptyStateText =
    extraction.state === 'skipped'
      ? '当前镜头已标记为无需提取，对白候选已按完成处理'
      : extraction.state === 'not_extracted'
        ? '当前还没有自动准备结果，可使用上方“重新提取/刷新候选”修复'
        : extraction.state === 'extracted_empty'
          ? '已执行提取，但当前没有识别到对白候选'
          : '当前没有待确认对白；如果需要，也可以直接补录最终对白'

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-white/80 px-4 py-4">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-slate-900 px-1.5 text-[11px] font-semibold text-white">
              2.2
            </span>
            <div className="text-sm font-medium text-slate-900">对白确认</div>
            <span
              className="inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium"
              style={{
                background:
                  dialogueStatus.tone === 'green'
                    ? '#dcfce7'
                    : dialogueStatus.tone === 'blue'
                      ? '#dbeafe'
                      : dialogueStatus.tone === 'default'
                        ? '#f1f5f9'
                        : '#fef3c7',
                color:
                  dialogueStatus.tone === 'green'
                    ? '#166534'
                    : dialogueStatus.tone === 'blue'
                      ? '#1d4ed8'
                      : dialogueStatus.tone === 'default'
                        ? '#475569'
                        : '#92400e',
              }}
            >
              {dialogueStatus.text}
            </span>
          </div>
          <div className="text-[11px] text-slate-500 mt-1">系统会自动写入可用对白；这里只处理仍需补录、修正或忽略的对白。</div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="small" icon={<PlusOutlined />} disabled={!!draftDialogueLine} onClick={onAddDraftDialogueLine}>
            新增对白
          </Button>
          {extractedDialogLines.length > 0 ? (
            <>
              <Button size="small" loading={batchDialogAdding} onClick={onAcceptAll}>
                全部接受
              </Button>
              <Button size="small" disabled={batchDialogAdding} onClick={onIgnoreAll}>
                全部忽略
              </Button>
            </>
          ) : null}
          {dialogLoading ? <Spin size="small" /> : null}
        </div>
      </div>

      <div className="space-y-2">
        {savedDialogLines.length === 0 && extractedDialogLines.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-5 text-xs text-slate-500">
            {emptyStateText}
          </div>
        ) : null}

        {savedDialogLines.length > 0 ? (
          <div className="space-y-2">
            {savedDialogLines
              .slice()
              .sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
              .map((l) => (
                <div key={l.id} className="flex items-start gap-2">
                  <Tooltip title="已保存">
                    <span className="mt-1 text-gray-500">
                      <SmileOutlined />
                    </span>
                  </Tooltip>
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    loading={!!dialogDeletingIds[l.id]}
                    onClick={() => onDeleteSavedDialogLine(l.id)}
                  />
                  <div className="w-36 shrink-0 text-xs text-gray-700 mt-1 truncate">
                    {dialogTitle(l.speaker_name, l.target_name)}
                  </div>
                  <Input.TextArea
                    value={l.text ?? ''}
                    onChange={(e) => onUpdateSavedDialogText(l.id, e.target.value)}
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    placeholder="对白内容"
                  />
                </div>
              ))}
          </div>
        ) : null}

        {draftDialogueLine ? (
          <div className="flex items-start gap-2">
            <Tooltip title="新增草稿，输入内容后自动保存">
              <span className="mt-1 text-slate-400">
                <PlusOutlined />
              </span>
            </Tooltip>
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              loading={draftDialogueSaving}
              onClick={onBlurDraftDialogueLine}
            />
            <Input
              className="w-36 shrink-0 text-xs"
              size="small"
              value={draftDialogueLine.speakerName}
              placeholder="说话人"
              onChange={(e) => onUpdateDraftDialogueLine({ speakerName: e.target.value })}
            />
            <Input.TextArea
              value={draftDialogueLine.text}
              onChange={(e) => onUpdateDraftDialogueLine({ text: e.target.value })}
              onBlur={onBlurDraftDialogueLine}
              autoSize={{ minRows: 1, maxRows: 4 }}
              placeholder="对白内容，输入后自动保存"
              disabled={draftDialogueSaving}
            />
          </div>
        ) : null}

        {extractedDialogLines.length > 0 ? (
          <div className="space-y-2">
            {extractedDialogLines.map((l) => (
              <div key={l.id} className="flex items-start gap-2">
                <Tooltip title="新提取">
                  <span className="mt-1 text-red-600">
                    <FireOutlined />
                  </span>
                </Tooltip>
                <Button
                  type="text"
                  size="small"
                  icon={<PlusOutlined />}
                  loading={!!dialogAddingKeys[String(l.id)]}
                  onClick={() => onAddExtractedDialogLine(l)}
                />
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  loading={!!dialogAddingKeys[String(l.id)]}
                  onClick={() => onIgnoreExtractedDialogLine(l)}
                />
                <div className="w-36 shrink-0 text-xs text-gray-700 mt-1 truncate">
                  {dialogTitle(l.speaker_name, l.target_name)}
                </div>
                <Input.TextArea
                  value={l.text ?? ''}
                  onChange={(e) => onUpdateExtractedDialogText(l.id, e.target.value)}
                  autoSize={{ minRows: 1, maxRows: 4 }}
                  placeholder="对白内容"
                />
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}
