import { StudioImageTasksService } from '../../../services/generated'
import { StudioEntitiesApi } from '../../../services/studioEntities'
import type { AssetEditPageBaseProps, BaseAsset, BaseAssetImage } from './components/AssetEditPageBase'

type AdapterConfig<TAsset extends BaseAsset, TImage extends BaseAssetImage> = Omit<
  AssetEditPageBaseProps<TAsset, TImage>,
  'assetId' | 'onNavigate'
>

type UpdateImagePayload = {
  file_id: string
  width?: number | null
  height?: number | null
  format?: string | null
}

function normalizeUpdateImagePayload(payload: UpdateImagePayload): UpdateImagePayload {
  return {
    ...payload,
    format: payload.format ?? 'png',
  }
}

export const assetAdapters = {
  character: {
    missingAssetIdText: '缺少 character_id',
    assetDisplayName: '角色',
    backTo: '/assets?tab=character',
    relationType: 'character_image',
    getAsset: async (id: string) => {
      const res = await StudioEntitiesApi.get('character', id)
      return (res.data ?? null) as any | null
    },
    updateAsset: async (id: string, payload) => {
      const res = await StudioEntitiesApi.update('character', id, payload as Record<string, unknown>)
      return (res.data ?? null) as any | null
    },
    listImages: async (id: string) => {
      const res = await StudioEntitiesApi.listImages('character', id, { page: 1, pageSize: 100 })
      return (res.data?.items ?? []) as any[]
    },
    createImageSlot: async (id: string, angle) => {
      await StudioEntitiesApi.createImage('character', id, { view_angle: angle })
    },
    updateImage: async (id: string, imageId: number, payload) => {
      await StudioEntitiesApi.updateImage('character', id, imageId, normalizeUpdateImagePayload(payload))
    },
    listImageCandidates: async (id: string, imageId: number) => {
      const res = await StudioEntitiesApi.listImageCandidates('character', id, imageId)
      return res.data ?? []
    },
    adoptImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.adoptImageCandidate('character', id, imageId, candidateId)
    },
    deleteImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.deleteImageCandidate('character', id, imageId, candidateId)
    },
    attachImageCandidates: async (id: string, imageId: number, fileIds: string[]) => {
      await StudioEntitiesApi.attachImageCandidates('character', id, imageId, { file_ids: fileIds, source_type: 'upload' })
    },
    createGenerationTask: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.createCharacterImageGenerationTaskApiV1StudioImageTasksCharactersCharacterIdImageTasksPost({
        characterId: id,
        requestBody: { image_id: imageId, model_id: null, prompt: payload.prompt, images: payload.images } as any,
      })
      return res.data?.task_id ?? null
    },
  } satisfies AdapterConfig<any, any>,
  actor: {
    missingAssetIdText: '缺少 actor_id',
    assetDisplayName: '演员',
    backTo: '/assets?tab=actor',
    relationType: 'actor_image',
    getAsset: async (id: string) => {
      const res = await StudioEntitiesApi.get('actor', id)
      return (res.data ?? null) as any | null
    },
    updateAsset: async (id: string, payload) => {
      const res = await StudioEntitiesApi.update('actor', id, payload as Record<string, unknown>)
      return (res.data ?? null) as any | null
    },
    listImages: async (id: string) => {
      const res = await StudioEntitiesApi.listImages('actor', id, { page: 1, pageSize: 100 })
      return (res.data?.items ?? []) as any[]
    },
    createImageSlot: async (id: string, angle) => {
      await StudioEntitiesApi.createImage('actor', id, { view_angle: angle })
    },
    updateImage: async (id: string, imageId: number, payload) => {
      await StudioEntitiesApi.updateImage('actor', id, imageId, normalizeUpdateImagePayload(payload))
    },
    listImageCandidates: async (id: string, imageId: number) => {
      const res = await StudioEntitiesApi.listImageCandidates('actor', id, imageId)
      return res.data ?? []
    },
    adoptImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.adoptImageCandidate('actor', id, imageId, candidateId)
    },
    deleteImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.deleteImageCandidate('actor', id, imageId, candidateId)
    },
    attachImageCandidates: async (id: string, imageId: number, fileIds: string[]) => {
      await StudioEntitiesApi.attachImageCandidates('actor', id, imageId, { file_ids: fileIds, source_type: 'upload' })
    },
    createGenerationTask: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.createActorImageGenerationTaskApiV1StudioImageTasksActorsActorIdImageTasksPost({
        actorId: id,
        requestBody: { image_id: imageId, model_id: null, prompt: payload.prompt, images: payload.images } as any,
      })
      return res.data?.task_id ?? null
    },
  } satisfies AdapterConfig<any, any>,
  scene: {
    missingAssetIdText: '缺少 scene_id',
    assetDisplayName: '场景',
    backTo: '/assets?tab=scene',
    relationType: 'scene_image',
    getAsset: async (id: string) => {
      const res = await StudioEntitiesApi.get('scene', id)
      return (res.data ?? null) as any | null
    },
    updateAsset: async (id: string, payload) => {
      const res = await StudioEntitiesApi.update('scene', id, payload as Record<string, unknown>)
      return (res.data ?? null) as any | null
    },
    listImages: async (id: string) => {
      const res = await StudioEntitiesApi.listImages('scene', id, { page: 1, pageSize: 100 })
      return (res.data?.items ?? []) as any[]
    },
    createImageSlot: async (id: string, angle) => {
      await StudioEntitiesApi.createImage('scene', id, { view_angle: angle })
    },
    updateImage: async (id: string, imageId: number, payload) => {
      await StudioEntitiesApi.updateImage('scene', id, imageId, normalizeUpdateImagePayload(payload))
    },
    listImageCandidates: async (id: string, imageId: number) => {
      const res = await StudioEntitiesApi.listImageCandidates('scene', id, imageId)
      return res.data ?? []
    },
    adoptImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.adoptImageCandidate('scene', id, imageId, candidateId)
    },
    deleteImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.deleteImageCandidate('scene', id, imageId, candidateId)
    },
    attachImageCandidates: async (id: string, imageId: number, fileIds: string[]) => {
      await StudioEntitiesApi.attachImageCandidates('scene', id, imageId, { file_ids: fileIds, source_type: 'upload' })
    },
    createGenerationTask: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.createAssetImageGenerationTaskApiV1StudioImageTasksAssetsAssetTypeAssetIdImageTasksPost({
        assetType: 'scene',
        assetId: id,
        requestBody: { image_id: imageId, prompt: payload.prompt, images: payload.images } as any,
      })
      return res.data?.task_id ?? null
    },
  } satisfies AdapterConfig<any, any>,
  prop: {
    missingAssetIdText: '缺少 prop_id',
    assetDisplayName: '道具',
    backTo: '/assets?tab=prop',
    relationType: 'prop_image',
    getAsset: async (id: string) => {
      const res = await StudioEntitiesApi.get('prop', id)
      return (res.data ?? null) as any | null
    },
    updateAsset: async (id: string, payload) => {
      const res = await StudioEntitiesApi.update('prop', id, payload as Record<string, unknown>)
      return (res.data ?? null) as any | null
    },
    listImages: async (id: string) => {
      const res = await StudioEntitiesApi.listImages('prop', id, { page: 1, pageSize: 100 })
      return (res.data?.items ?? []) as any[]
    },
    createImageSlot: async (id: string, angle) => {
      await StudioEntitiesApi.createImage('prop', id, { view_angle: angle })
    },
    updateImage: async (id: string, imageId: number, payload) => {
      await StudioEntitiesApi.updateImage('prop', id, imageId, normalizeUpdateImagePayload(payload))
    },
    listImageCandidates: async (id: string, imageId: number) => {
      const res = await StudioEntitiesApi.listImageCandidates('prop', id, imageId)
      return res.data ?? []
    },
    adoptImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.adoptImageCandidate('prop', id, imageId, candidateId)
    },
    deleteImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.deleteImageCandidate('prop', id, imageId, candidateId)
    },
    attachImageCandidates: async (id: string, imageId: number, fileIds: string[]) => {
      await StudioEntitiesApi.attachImageCandidates('prop', id, imageId, { file_ids: fileIds, source_type: 'upload' })
    },
    createGenerationTask: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.createAssetImageGenerationTaskApiV1StudioImageTasksAssetsAssetTypeAssetIdImageTasksPost({
        assetType: 'prop',
        assetId: id,
        requestBody: { image_id: imageId, prompt: payload.prompt, images: payload.images } as any,
      })
      return res.data?.task_id ?? null
    },
  } satisfies AdapterConfig<any, any>,
  costume: {
    missingAssetIdText: '缺少 costume_id',
    assetDisplayName: '服装',
    backTo: '/assets?tab=costume',
    relationType: 'costume_image',
    getAsset: async (id: string) => {
      const res = await StudioEntitiesApi.get('costume', id)
      return (res.data ?? null) as any | null
    },
    updateAsset: async (id: string, payload) => {
      const res = await StudioEntitiesApi.update('costume', id, payload as Record<string, unknown>)
      return (res.data ?? null) as any | null
    },
    listImages: async (id: string) => {
      const res = await StudioEntitiesApi.listImages('costume', id, { page: 1, pageSize: 100 })
      return (res.data?.items ?? []) as any[]
    },
    createImageSlot: async (id: string, angle) => {
      await StudioEntitiesApi.createImage('costume', id, { view_angle: angle })
    },
    updateImage: async (id: string, imageId: number, payload) => {
      await StudioEntitiesApi.updateImage('costume', id, imageId, normalizeUpdateImagePayload(payload))
    },
    listImageCandidates: async (id: string, imageId: number) => {
      const res = await StudioEntitiesApi.listImageCandidates('costume', id, imageId)
      return res.data ?? []
    },
    adoptImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.adoptImageCandidate('costume', id, imageId, candidateId)
    },
    deleteImageCandidate: async (id: string, imageId: number, candidateId: number) => {
      await StudioEntitiesApi.deleteImageCandidate('costume', id, imageId, candidateId)
    },
    attachImageCandidates: async (id: string, imageId: number, fileIds: string[]) => {
      await StudioEntitiesApi.attachImageCandidates('costume', id, imageId, { file_ids: fileIds, source_type: 'upload' })
    },
    createGenerationTask: async (id: string, imageId: number, payload: { prompt: string; images: string[] }) => {
      const res = await StudioImageTasksService.createAssetImageGenerationTaskApiV1StudioImageTasksAssetsAssetTypeAssetIdImageTasksPost({
        assetType: 'costume',
        assetId: id,
        requestBody: { image_id: imageId, prompt: payload.prompt, images: payload.images } as any,
      })
      return res.data?.task_id ?? null
    },
  } satisfies AdapterConfig<any, any>,
}
