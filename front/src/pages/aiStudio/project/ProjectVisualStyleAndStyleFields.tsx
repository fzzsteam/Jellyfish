import { Form, Select } from 'antd'

export type ProjectVisualStyleChoice = string

export type OptionItem = { value: string; label: string }
export type ProjectStyleOptionsByVisual = Record<string, OptionItem[]>
export type ProjectStyleFieldOptions = {
  visualStyles: OptionItem[]
  stylesByVisual: ProjectStyleOptionsByVisual
  defaultStyleByVisual?: Record<string, string>
}

export const PROJECT_STYLE_OPTIONS_BY_VISUAL: ProjectStyleOptionsByVisual = {
  现实: [
    { value: '真人都市', label: '真人都市' },
    { value: '真人科幻', label: '真人科幻' },
    { value: '真人古装', label: '真人古装' },
    { value: '真人悬疑', label: '真人悬疑' },
    { value: '真人甜宠', label: '真人甜宠' },
    { value: '真人热血', label: '真人热血' },
  ],
  动漫: [
    { value: '动漫科幻', label: '动漫科幻' },
    { value: '动漫3D', label: '动漫3D' },
    { value: '动漫仙侠', label: '动漫仙侠' },
    { value: '动漫赛博', label: '动漫赛博' },
    { value: '动漫治愈', label: '动漫治愈' },
  ],
  '2D': [
    { value: '2D日漫', label: '2D日漫' },
    { value: '2D国潮', label: '2D国潮' },
    { value: '2D扁平', label: '2D扁平' },
    { value: '2D都市恋爱', label: '2D都市恋爱' },
  ],
  国风: [
    { value: '国漫', label: '国漫' },
    { value: '水墨画', label: '水墨画' },
    { value: '国风玄幻', label: '国风玄幻' },
    { value: '国风古韵', label: '国风古韵' },
  ],
  '3D': [
    { value: '动漫3D', label: '动漫3D' },
    { value: '3D少儿', label: '3D少儿' },
    { value: '3D奇幻', label: '3D奇幻' },
  ],
}
const DEFAULT_VISUAL_STYLE_OPTIONS: OptionItem[] = [
  { value: '现实', label: '现实' },
  { value: '动漫', label: '动漫' },
  { value: '国风', label: '国风' },
  { value: '2D', label: '2D' },
  { value: '3D', label: '3D' },
]
const DEFAULT_STYLE_BY_VISUAL: Record<string, string> = {
  现实: PROJECT_STYLE_OPTIONS_BY_VISUAL['现实']?.[0]?.value ?? '',
  动漫: PROJECT_STYLE_OPTIONS_BY_VISUAL['动漫']?.[0]?.value ?? '',
}

type FormModeProps = {
  form: any
  disabled?: boolean
  options?: ProjectStyleFieldOptions
}

type ControlledModeProps = {
  visual_style: ProjectVisualStyleChoice
  style: string
  onChange: (next: { visual_style: ProjectVisualStyleChoice; style: string }) => void
  disabled?: boolean
  visualStyleLabel?: string
  styleLabel?: string
  options?: ProjectStyleFieldOptions
}

function resolveOptions(options?: ProjectStyleFieldOptions): ProjectStyleFieldOptions {
  return {
    visualStyles: options?.visualStyles?.length ? options.visualStyles : DEFAULT_VISUAL_STYLE_OPTIONS,
    stylesByVisual:
      options?.stylesByVisual && Object.keys(options.stylesByVisual).length
        ? options.stylesByVisual
        : PROJECT_STYLE_OPTIONS_BY_VISUAL,
    defaultStyleByVisual:
      options?.defaultStyleByVisual && Object.keys(options.defaultStyleByVisual).length
        ? options.defaultStyleByVisual
        : DEFAULT_STYLE_BY_VISUAL,
  }
}

function getDefaultStyle(visual: string, options: ProjectStyleFieldOptions): string {
  return (
    options.defaultStyleByVisual?.[visual] ??
    options.stylesByVisual[visual]?.[0]?.value ??
    ''
  )
}

export function ProjectVisualStyleAndStyleFields(props: FormModeProps | ControlledModeProps) {
  const disabled = props.disabled
  const resolvedOptions = resolveOptions(props.options)

  if ('form' in props) {
    const { form } = props

    return (
      <>
        <Form.Item name="visual_style" label="视觉风格" rules={[{ required: true }]}>
          <Select
            disabled={disabled}
            onChange={(v: string) => {
              const nextStyle = getDefaultStyle(v, resolvedOptions)
              form.setFieldValue('style', nextStyle)
            }}
            options={resolvedOptions.visualStyles}
          />
        </Form.Item>

        <Form.Item noStyle shouldUpdate={(prev, next) => prev.visual_style !== next.visual_style}>
          {({ getFieldValue }) => {
            const visual = (getFieldValue('visual_style') as string | undefined) ?? resolvedOptions.visualStyles[0]?.value ?? '现实'
            return (
              <Form.Item name="style" label="视频风格" rules={[{ required: true }]}>
                <Select disabled={disabled} options={resolvedOptions.stylesByVisual[visual] ?? []} />
              </Form.Item>
            )
          }}
        </Form.Item>
      </>
    )
  }

  const { visual_style, style, onChange, visualStyleLabel, styleLabel } = props

  return (
    <div className="space-y-3">
      <div>
        <span className="text-gray-600 text-sm">{visualStyleLabel ?? '视觉风格'}</span>
        <Select
          className="mt-1 w-full"
          disabled={disabled}
          value={visual_style}
          onChange={(v) => {
            const nextVisual = v as ProjectVisualStyleChoice
            onChange({ visual_style: nextVisual, style: getDefaultStyle(nextVisual, resolvedOptions) })
          }}
          options={resolvedOptions.visualStyles}
        />
      </div>
      <div>
        <span className="text-gray-600 text-sm">{styleLabel ?? '视频风格'}</span>
        <Select
          className="mt-1 w-full"
          disabled={disabled}
          value={style}
          onChange={(v) => onChange({ visual_style, style: String(v) })}
          options={resolvedOptions.stylesByVisual[visual_style] ?? []}
        />
      </div>
    </div>
  )
}
