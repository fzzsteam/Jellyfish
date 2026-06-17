import { AssetTypeTab } from './AssetTypeTab'
import { useNavigate } from 'react-router-dom'
import { StudioEntitiesApi } from '../../../../services/studioEntities'

export function CharactersTab() {
  const navigate = useNavigate()

  return (
    <AssetTypeTab
      label="角色"
      tabKey="character"
      listAssets={async ({ q, page, pageSize }) => {
        const res = await StudioEntitiesApi.list('character', { q: q ?? null, page, pageSize })
        return { items: (res.data?.items ?? []) as any[], total: res.data?.pagination.total ?? 0 }
      }}
      createAsset={async (payload) => {
        const res = await StudioEntitiesApi.create('character', payload as Record<string, unknown>)
        if (!res.data) throw new Error('empty character')
        return res.data as any
      }}
      updateAsset={async (id, payload) => {
        const res = await StudioEntitiesApi.update('character', id, payload as Record<string, unknown>)
        if (!res.data) throw new Error('empty character')
        return res.data as any
      }}
      deleteAsset={async (id) => {
        await StudioEntitiesApi.remove('character', id)
      }}
      onEditAsset={(asset) => {
        navigate(`/assets/characters/${asset.id}/edit`)
      }}
    />
  )
}
