import type React from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Spin } from 'antd'
import { buildFileDownloadUrl } from '../utils'

export type MentionAssetKind = 'prop' | 'costume' | 'scene' | 'character'

export type MentionImageOption = {
  id: string
  file_id: string
  label: string
  subtitle?: string | null
}

interface MentionEditorProps {
  value: string
  onChange: (text: string, fileIds: string[]) => void
  disabled?: boolean
  placeholder?: string
  loadImagesByKind: (kind: MentionAssetKind) => Promise<MentionImageOption[]>
  minRows?: number
}

const MENTION_CATEGORIES: Array<{ kind: MentionAssetKind; label: string; description: string }> = [
  { kind: 'prop', label: '道具', description: '引用道具资产图片' },
  { kind: 'costume', label: '服装', description: '引用服装资产图片' },
  { kind: 'scene', label: '场景', description: '引用场景资产图片' },
  { kind: 'character', label: '角色', description: '引用角色资产图片' },
]

// Recursively extracts plain text from the editor, skipping image chip spans.
function getEditorText(el: HTMLElement): string {
  let text = ''
  for (const node of el.childNodes) {
    if (node.nodeType === Node.TEXT_NODE) {
      text += node.textContent ?? ''
    } else if (node instanceof HTMLElement) {
      if (node.dataset.fileId) {
        // Image chips are reference metadata, so they are omitted from plain text.
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
 * Rich-text description editor that supports "@" to insert inline asset image chips.
 * The picker first selects an asset category, then one image from that category.
 */
export function MentionEditor({
  value,
  onChange,
  disabled,
  placeholder,
  loadImagesByKind,
  minRows = 4,
}: MentionEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  // Prevents the external-value sync effect from clobbering user edits.
  const isInternalRef = useRef(false)
  // Stores the Range covering the "@" character so it can be replaced by a chip.
  const atRangeRef = useRef<Range | null>(null)

  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerMode, setPickerMode] = useState<'category' | 'images'>('category')
  const [selectedKind, setSelectedKind] = useState<MentionAssetKind | null>(null)
  const [imageOptions, setImageOptions] = useState<MentionImageOption[]>([])
  const [pickerLoading, setPickerLoading] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const [hasContent, setHasContent] = useState(false)

  // Sync external value changes into the editor without overwriting active typing.
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

  const buildChip = useCallback((option: MentionImageOption): HTMLElement => {
    const chip = document.createElement('span')
    chip.contentEditable = 'false'
    chip.dataset.fileId = option.file_id
    chip.style.cssText =
      'display:inline-flex;align-items:center;vertical-align:middle;margin:0 2px;' +
      'border-radius:4px;overflow:hidden;border:1.5px solid #bfdbfe;background:#eff6ff;user-select:none;cursor:default;'

    const img = document.createElement('img')
    img.src = buildFileDownloadUrl(option.file_id) ?? ''
    img.alt = option.label || '参考图'
    img.style.cssText = 'width:24px;height:24px;object-fit:cover;display:block;'
    chip.appendChild(img)

    return chip
  }, [])

  const insertChip = useCallback(
    (option: MentionImageOption) => {
      if (!option.file_id || !editorRef.current) return

      const chip = buildChip(option)

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
      setPickerMode('category')
      setSelectedKind(null)
      setImageOptions([])
      notifyChange()
    },
    [buildChip, notifyChange],
  )

  const openPicker = useCallback(() => {
    setPickerOpen(true)
    setHighlighted(0)
    setPickerMode('category')
    setSelectedKind(null)
    setImageOptions([])
    setPickerLoading(false)
  }, [])

  const closePicker = useCallback(() => {
    setPickerOpen(false)
    setPickerMode('category')
    setSelectedKind(null)
    setImageOptions([])
    setPickerLoading(false)
    atRangeRef.current = null
  }, [])

  // Loads all images for one asset category after the user confirms the first-level menu.
  const selectCategory = useCallback(
    async (kind: MentionAssetKind) => {
      setPickerMode('images')
      setSelectedKind(kind)
      setHighlighted(0)
      setPickerLoading(true)
      setImageOptions([])
      try {
        const list = await loadImagesByKind(kind)
        setImageOptions(list)
      } catch {
        setImageOptions([])
      } finally {
        setPickerLoading(false)
      }
    },
    [loadImagesByKind],
  )

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
        openPicker()
      }
    }
  }

  const pickerStateRef = useRef({
    pickerOpen,
    pickerMode,
    pickerLoading,
    imageOptions,
    highlighted,
    insertChip,
    selectCategory,
  })
  pickerStateRef.current = {
    pickerOpen,
    pickerMode,
    pickerLoading,
    imageOptions,
    highlighted,
    insertChip,
    selectCategory,
  }

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const {
      pickerOpen: open,
      pickerMode: mode,
      pickerLoading: loading,
      imageOptions: options,
      highlighted: hi,
      insertChip: ins,
      selectCategory: chooseCategory,
    } = pickerStateRef.current
    if (!open) return

    const optionCount = mode === 'category' ? MENTION_CATEGORIES.length : options.length
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted((i) => Math.min(i + 1, Math.max(optionCount - 1, 0)))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (loading) return
      if (mode === 'category') {
        const category = MENTION_CATEGORIES[hi]
        if (category) void chooseCategory(category.kind)
      } else {
        const option = options[hi]
        if (option) ins(option)
      }
    } else if (e.key === 'Backspace' && mode === 'images') {
      e.preventDefault()
      setPickerMode('category')
      setSelectedKind(null)
      setImageOptions([])
      setHighlighted(0)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      closePicker()
    }
  }, [closePicker])

  const minH = `${minRows * 1.625}rem`
  const selectedKindLabel =
    MENTION_CATEGORIES.find((item) => item.kind === selectedKind)?.label ?? ''

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
            maxHeight: 260,
            border: '1px solid #374151',
            boxShadow: '0 -4px 12px rgba(0,0,0,0.15)',
          }}
          onMouseDown={(e) => e.preventDefault()}
        >
          {pickerMode === 'category' ? (
            <div className="min-w-48 p-1">
              {MENTION_CATEGORIES.map((category, idx) => (
                <div
                  key={category.kind}
                  className="cursor-pointer rounded px-3 py-2"
                  style={{
                    background: idx === highlighted ? '#eff6ff' : '#fff',
                    color: idx === highlighted ? '#1677ff' : undefined,
                  }}
                  onMouseEnter={() => setHighlighted(idx)}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    void selectCategory(category.kind)
                  }}
                >
                  <div className="text-sm font-medium">{category.label}</div>
                  <div className="text-xs text-gray-400">{category.description}</div>
                </div>
              ))}
            </div>
          ) : pickerLoading ? (
            <div className="flex justify-center py-4 px-8">
              <Spin size="small" />
            </div>
          ) : imageOptions.length === 0 ? (
            <div className="text-sm text-gray-500 text-center py-4 px-6">
              暂无{selectedKindLabel}资产图片
            </div>
          ) : (
            <div
              className="flex flex-wrap gap-2 p-2"
              style={{ maxWidth: 1192 }}
            >
              {imageOptions.map((option, idx) => (
                <div
                  key={option.id}
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
                    insertChip(option)
                  }}
                >
                  <img
                    src={buildFileDownloadUrl(option.file_id) ?? ''}
                    alt={option.label}
                    className="w-full object-cover"
                    style={{ height: 54 }}
                  />
                  <div className="text-xs text-gray-500 text-center truncate px-1 py-0.5">
                    {option.subtitle || option.label}
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
