import { StudioFilesService } from '../../../services/generated'
import { StudioEntitiesApi } from '../../../services/studioEntities'
import { generateUUID } from '../../../utils'

type EntityType = 'actor' | 'character' | 'scene' | 'prop' | 'costume'

type BulkUploadOptions = {
  entityType: EntityType
  files: File[]
  visualStyle: string
  style: string
}

type BulkUploadResult = {
  createdCount: number
  failedCount: number
}

function fileNameWithoutExtension(fileName: string): string {
  const trimmed = fileName.trim()
  const lastDot = trimmed.lastIndexOf('.')
  if (lastDot <= 0) return trimmed || '未命名资产'
  return trimmed.slice(0, lastDot).trim() || trimmed
}

function isImageFile(file: File): boolean {
  if (file.type.startsWith('image/')) return true
  return /\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(file.name)
}

function entityIdForType(entityType: EntityType): string {
  if (entityType === 'actor') return generateUUID()
  return `asset_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

async function ensureFrontImageSlot(entityType: EntityType, entityId: string): Promise<number | null> {
  const images = await StudioEntitiesApi.listImages(entityType, entityId, { page: 1, pageSize: 100 })
  const existing = (images.data?.items ?? []).find((item: any) => item?.view_angle === 'FRONT')
  if (existing?.id) return Number(existing.id)

  const created = await StudioEntitiesApi.createImage(entityType, entityId, { view_angle: 'FRONT' })
  const createdId = (created.data as any)?.id
  return typeof createdId === 'number' ? createdId : null
}

export async function bulkUploadAssetImages({
  entityType,
  files,
  visualStyle,
  style,
}: BulkUploadOptions): Promise<BulkUploadResult> {
  const imageFiles = files.filter(isImageFile)
  let createdCount = 0
  let failedCount = files.length - imageFiles.length

  for (const file of imageFiles) {
    try {
      const uploadRes = await StudioFilesService.uploadFileApiApiV1StudioFilesUploadPost({
        formData: { file } as any,
        name: file.name,
      })
      const fileId = uploadRes.data?.id
      if (!fileId) throw new Error('missing uploaded file id')

      const entityRes = await StudioEntitiesApi.create(entityType, {
        id: entityIdForType(entityType),
        name: fileNameWithoutExtension(file.name),
        description: '',
        tags: [],
        view_count: 1,
        visual_style: visualStyle,
        style,
        prompt_template_id: null,
      })
      const entityId = String((entityRes.data as any)?.id ?? '')
      if (!entityId) throw new Error('missing created entity id')

      const imageId = await ensureFrontImageSlot(entityType, entityId)
      if (!imageId) throw new Error('missing image slot id')

      await StudioEntitiesApi.updateImage(entityType, entityId, imageId, {
        file_id: fileId,
        format: 'png',
      })
      await StudioEntitiesApi.attachImageCandidates(entityType, entityId, imageId, {
        file_ids: [fileId],
        source_type: 'upload',
        source_ref: `asset-list-bulk-upload:${entityId}:${imageId}:${Date.now()}`,
        auto_adopt_if_empty: false,
      })
      createdCount += 1
    } catch {
      failedCount += 1
    }
  }

  return { createdCount, failedCount }
}
