import type React from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Spin } from 'antd'
import type { AssetImageCandidateRead } from '../../../../services/generated'
import { buildFileDownloadUrl } from '../utils'

interface MentionEditorProps {
  value: string
  onChange: (text: string, fileIds: string[]) => void
  disabled?: boolean
  placeholder?: string
  loadCandidates: () => Promise<AssetImageCandidateRead[]>
  minRows?: number
}

// Recursively extracts plain text from the editor, skipping image chip spans.
function getEditorText(el: HTMLElement): string {
  let text = ''
  for (const node of el.childNodes) {
    if (node.nodeType === Node.TEXT_NODE) {
      text += node.textContent ?? ''
    } else if (node instanceof HTMLElement) {
      if (node.dataset.fileId) {
        // chip — omit from text; file_id is tracked separately
      } else if (node.tagName === 'BR') {
        text += '\n'
      } else if (node.tagName === 'DIV' || node.tagName === 'P') {
        const inner = getEditorText(node)
        if (inner) text += (text ? '\n' : '') + inner
      } else {
        text += getEditorText(node)
      }
    }
  }
  return text
}

// Collects unique file_ids from all chip spans currently in the editor.
function getEditorFileIds(el: HTMLElement): string[] {
  const ids: string[] = []
  el.querySelectorAll<HTMLElement>('[data-file-id]').forEach((chip) => {
    const fid = chip.dataset.fileId
    if (fid && !ids.includes(fid)) ids.push(fid)
  })
  return ids
}

/**
 * Rich-text description editor that supports "@" to insert inline candidate image chips.
 * Selected images appear as thumbnails inline, and their file_ids are reported via onChange
 * alongside the plain text, for use as generation reference images.
 */
export function MentionEditor({
  value,
  onChange,
  disabled,
  placeholder,
  loadCandidates,
  minRows = 4,
}: MentionEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  // Prevents the external-value sync effect from clobbering user edits.
  const isInternalRef = useRef(false)
  // Stores the Range covering the "@" character so it can be replaced by a chip.
  const atRangeRef = useRef<Range | null>(null)

  const [pickerOpen, setPickerOpen] = useState(false)
  const [candidates, setCandidates] = useState<AssetImageCandidateRead[]>([])
  const [pickerLoading, setPickerLoading] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const [hasContent, setHasContent] = useState(false)

  // Sync external value changes (loadData, smart-detect apply) into the editor.
  // Internal typing is guarded by isInternalRef so this only fires on true external resets.
  useEffect(() => {
    if (isInternalRef.current) {
      isInternalRef.current = false
      return
    }
    const el = editorRef.current
    if (!el) return
    const current = getEditorText(el)
    if (current !== value) {
      el.textContent = value
      setHasContent(Boolean(value))
    }
  }, [value])

  const notifyChange = useCallback(() => {
    const el = editorRef.current
    if (!el) return
    const text = getEditorText(el)
    const fileIds = getEditorFileIds(el)
    const anyContent =
      el.childNodes.length > 0 && (Boolean(el.textContent) || fileIds.length > 0)
    setHasContent(anyContent)
    isInternalRef.current = true
    onChange(text, fileIds)
  }, [onChange])

  const buildChip = useCallback(
    (candidate: AssetImageCandidateRead, onDelete: () => void): HTMLElement => {
      const chip = document.createElement('span')
      chip.contentEditable = 'false'
      chip.dataset.fileId = candidate.file_id ?? ''
      chip.style.cssText =
        'display:inline-flex;align-items:center;vertical-align:middle;margin:0 2px;' +
        'border-radius:4px;overflow:hidden;border:1.5px solid #bfdbfe;background:#eff6ff;user-select:none;cursor:default;'

      void onDelete // referenced so the callback isn't dead code

      const img = document.createElement('img')
      img.src = buildFileDownloadUrl(candidate.file_id) ?? ''
      img.alt = '参考图'
      img.style.cssText = 'width:24px;height:24px;object-fit:cover;display:block;'
      chip.appendChild(img)

      return chip
    },
    [],
  )

  const insertChip = useCallback(
    (candidate: AssetImageCandidateRead) => {
      if (!candidate.file_id || !editorRef.current) return

      const chip = buildChip(candidate, () => {
        chip.remove()
        notifyChange()
      })

      if (atRangeRef.current) {
        atRangeRef.current.deleteContents()
        atRangeRef.current.insertNode(chip)
        // Place cursor right after the newly inserted chip.
        const sel = window.getSelection()
        const range = document.createRange()
        range.setStartAfter(chip)
        range.collapse(true)
        sel?.removeAllRanges()
        sel?.addRange(range)
      }

      atRangeRef.current = null
      setPickerOpen(false)
      notifyChange()
    },
    [buildChip, notifyChange],
  )

  const openPicker = useCallback(async () => {
    setPickerOpen(true)
    setHighlighted(0)
    setPickerLoading(true)
    setCandidates([])
    try {
      const list = await loadCandidates()
      setCandidates(list)
    } catch {
      // Show empty state in picker
    } finally {
      setPickerLoading(false)
    }
  }, [loadCandidates])

  const handleInput = () => {
    notifyChange()
    const sel = window.getSelection()
    if (!sel?.rangeCount) return
    const range = sel.getRangeAt(0)
    const { startContainer, startOffset } = range
    if (startContainer.nodeType === Node.TEXT_NODE && startOffset > 0) {
      const text = startContainer.textContent ?? ''
      if (text[startOffset - 1] === '@') {
        // Capture the "@" range so insertChip can replace it.
        const atRange = document.createRange()
        atRange.setStart(startContainer, startOffset - 1)
        atRange.setEnd(startContainer, startOffset)
        atRangeRef.current = atRange
        void openPicker()
      }
    }
  }

  // Use a ref to always read the latest picker state inside the keydown handler
  // without stale-closure issues caused by React batching or useCallback deps.
  const pickerStateRef = useRef({ pickerOpen, candidates, highlighted, insertChip })
  pickerStateRef.current = { pickerOpen, candidates, highlighted, insertChip }

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const { pickerOpen: open, candidates: cands, highlighted: hi, insertChip: ins } = pickerStateRef.current
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted((i) => Math.min(i + 1, cands.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const c = cands[hi]
      if (c) ins(c)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setPickerOpen(false)
      atRangeRef.current = null
    }
  }, [])

  const minH = `${minRows * 1.625}rem`

  return (
    <div
      ref={containerRef}
      className="relative rounded cursor-text"
      style={{ border: '1px solid #d9d9d9', transition: 'border-color 0.2s' }}
      onFocus={() => { if (containerRef.current) containerRef.current.style.borderColor = '#1677ff' }}
      onBlur={() => { if (containerRef.current) containerRef.current.style.borderColor = '#d9d9d9' }}
      onClick={() => editorRef.current?.focus()}
    >
      {!hasContent && placeholder && (
        <div className="absolute top-2 left-3 text-gray-400 text-sm pointer-events-none select-none">
          {placeholder}
        </div>
      )}
      <div
        ref={editorRef}
        contentEditable={!disabled}
        suppressContentEditableWarning
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        className="p-2 outline-none text-sm"
        style={{
          minHeight: minH,
          lineHeight: '1.7',
          wordBreak: 'break-word',
          color: disabled ? 'rgba(0,0,0,0.25)' : undefined,
          cursor: disabled ? 'not-allowed' : 'text',
        }}
      />
      {pickerOpen && (
        <div
          className="absolute z-50 left-0 bg-white rounded overflow-y-auto"
          style={{
            bottom: '100%',
            marginBottom: 4,
            width: 'max-content',
            maxWidth: '100%',
            maxHeight: 220,
            border: '1px solid #374151',
            boxShadow: '0 -4px 12px rgba(0,0,0,0.15)',
          }}
          onMouseDown={(e) => e.preventDefault()}
        >
          {pickerLoading ? (
            <div className="flex justify-center py-4">
              <Spin size="small" />
            </div>
          ) : candidates.length === 0 ? (
            <div className="text-sm text-gray-500 text-center py-4">
              暂无候选图片，请先在候选池中添加图片
            </div>
          ) : (
            <div className="flex flex-wrap gap-2 p-2">
              {candidates.map((c, idx) => (
                <div
                  key={c.id}
                  className="rounded overflow-hidden cursor-pointer"
                  style={{
                    width: 72,
                    border: idx === highlighted ? '2px solid #3b82f6' : '1.5px solid #bfdbfe',
                    background: idx === highlighted ? '#eff6ff' : '#fff',
                    transition: 'border-color 0.12s, background 0.12s',
                  }}
                  onMouseEnter={() => setHighlighted(idx)}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    insertChip(c)
                  }}
                >
                  <img
                    src={buildFileDownloadUrl(c.file_id) ?? ''}
                    alt={`候选图${idx + 1}`}
                    className="w-full object-cover"
                    style={{ height: 54 }}
                  />
                  <div className="text-xs text-gray-500 text-center truncate px-1 py-0.5">
                    候选图{idx + 1}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
