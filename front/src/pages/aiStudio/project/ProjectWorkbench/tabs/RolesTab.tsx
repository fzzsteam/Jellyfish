import { useEffect, useMemo, useState } from 'react'
import { Card, Button, Empty, Modal, Input, message, Space, Select, Pagination } from 'antd'
import { EditOutlined, LinkOutlined, PlusOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  StudioProjectsService,
  StudioShotLinksService,
} from '../../../../../services/generated'
import type { ProjectActorLinkRead, ProjectCostumeLinkRead } from '../../../../../services/generated'
import { useProjectCharacters, newId } from '../hooks/useProjectData'
import { resolveAssetUrl } from '../../../assets/utils'
import { DisplayImageCard } from '../../../assets/components/DisplayImageCard'
import { StudioEntitiesApi } from '../../../../../services/studioEntities'
import {
  ProjectVisualStyleAndStyleFields,
  type ProjectVisualStyleChoice,
} from '../../../project/ProjectVisualStyleAndStyleFields'
import { useProjectStyleOptions } from '../../../project/useProjectStyleOptions'
import { encodeWorkbenchAssetEditReturnTo } from '../utils/workbenchAssetReturnTo'

type ActorLike = {
  id: string
  name: string
  description?: string | null
  thumbnail?: string
}

type CostumeLike = {
  id: string
  name: string
  description?: string | null
  thumbnail?: string
}

type CharacterLike = {
  id: string
  name: string
  description?: string | null
  thumbnail?: string
}

function notifyShotAssetCreatedAndLinked(payload: {
  projectId?: string
  chapterId?: string | null
  shotId?: string | null
  assetId?: string
  assetName: string
}) {
  if (!payload.projectId || !payload.chapterId || !payload.shotId) return
  try {
    window.opener?.postMessage(
      {
        type: 'studio-shot-asset-created-and-linked',
        projectId: payload.projectId,
        chapterId: payload.chapterId,
        shotId: payload.shotId,
        assetId: payload.assetId ?? null,
        assetName: payload.assetName,
      },
      window.location.origin,
    )
  } catch {
    // 跨窗口通知失败不阻塞角色创建成功。
  }
}

export function RolesTab() {
  const { options: projectStyleOptions, defaultVisualStyle, getDefaultStyle } = useProjectStyleOptions()
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const { characters, loading, refresh } = useProjectCharacters(projectId)

  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [pendingShotLinkShotId, setPendingShotLinkShotId] = useState<string | null>(null)
  const [pendingShotLinkChapterId, setPendingShotLinkChapterId] = useState<string | null>(null)
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formActorId, setFormActorId] = useState<string | undefined>(undefined)
  const [formCostumeId, setFormCostumeId] = useState<string | undefined>(undefined)

  const [projectActorLinks, setProjectActorLinks] = useState<ProjectActorLinkRead[]>([])
  const [projectCostumeLinks, setProjectCostumeLinks] = useState<ProjectCostumeLinkRead[]>([])
  const [actorsById, setActorsById] = useState<Record<string, ActorLike>>({})
  const [costumesById, setCostumesById] = useState<Record<string, CostumeLike>>({})
  const [loadingLinks, setLoadingLinks] = useState(false)
  const [projectVisualStyle, setProjectVisualStyle] = useState<ProjectVisualStyleChoice>(defaultVisualStyle as ProjectVisualStyleChoice)
  const [projectStyle, setProjectStyle] = useState<string>(getDefaultStyle(defaultVisualStyle))
  const [formVisualStyle, setFormVisualStyle] = useState<ProjectVisualStyleChoice>(defaultVisualStyle as ProjectVisualStyleChoice)
  const [formStyle, setFormStyle] = useState<string>(getDefaultStyle(defaultVisualStyle))

  // 从资产库关联相关状态
  const [linkModalOpen, setLinkModalOpen] = useState(false)
  const [libraryCharacters, setLibraryCharacters] = useState<CharacterLike[]>([])
  const [libraryLoading, setLibraryLoading] = useState(false)
  const [librarySearch, setLibrarySearch] = useState('')
  const [linkingId, setLinkingId] = useState<string | null>(null)

  useEffect(() => {
    const create = searchParams.get('create')
    const name = searchParams.get('name') ?? ''
    const desc = searchParams.get('desc') ?? ''
    const tab = searchParams.get('tab')
    const visualStyle = (searchParams.get('visualStyle')?.trim() || '') as ProjectVisualStyleChoice | ''
    const style = searchParams.get('style')?.trim() ?? ''
    if (create === '1' && tab === 'roles') {
      setFormName(name)
      setFormDesc(desc)
      setFormActorId(undefined)
      setFormCostumeId(undefined)
      const nextVisual = visualStyle || projectVisualStyle
      setFormVisualStyle(nextVisual)
      setFormStyle(style || projectStyle || getDefaultStyle(nextVisual))
      const shotIdFromUrl = searchParams.get('shotId')?.trim() ?? ''
      const chapterIdFromUrl = searchParams.get('chapterId')?.trim() ?? ''
      setPendingShotLinkShotId(shotIdFromUrl || null)
      setPendingShotLinkChapterId(chapterIdFromUrl || null)
      setCreateOpen(true)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.delete('create')
          next.delete('name')
          next.delete('desc')
          next.delete('chapterId')
          next.delete('shotId')
          next.delete('visualStyle')
          next.delete('style')
          return next
        },
        { replace: true },
      )
    }
  }, [getDefaultStyle, projectStyle, projectVisualStyle, searchParams, setSearchParams])


  const [creatingBlank, setCreatingBlank] = useState(false)
  const handleCreateBlank = async () => {
    if (!projectId || creatingBlank) return
    setCreatingBlank(true)
    try {
      const id = newId('char')
      const res = await StudioEntitiesApi.create('character', { id, project_id: projectId, name: '未命名角色' })
      const createdId = (res.data as { id?: string } | undefined)?.id ?? id
      navigate(`/assets/characters/${createdId}/edit?returnTo=${encodeWorkbenchAssetEditReturnTo(projectId, 'roles')}`)
    } catch {
      message.error('新建角色失败')
    } finally {
      setCreatingBlank(false)
    }
  }

  const loadProjectLinks = async () => {
    if (!projectId) return
    setLoadingLinks(true)
    try {
      const [actorRes, costumeRes] = await Promise.all([
        StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
          entityType: 'actor',
          projectId,
          chapterId: null,
          shotId: null,
          assetId: null,
          order: null,
          isDesc: false,
          page: 1,
          pageSize: 100,
        }),
        StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
          entityType: 'costume',
          projectId,
          chapterId: null,
          shotId: null,
          assetId: null,
          order: null,
          isDesc: false,
          page: 1,
          pageSize: 100,
        }),
      ])
      const actorLinks = (actorRes.data?.items ?? []) as ProjectActorLinkRead[]
      const costumeLinks = (costumeRes.data?.items ?? []) as ProjectCostumeLinkRead[]
      setProjectActorLinks(actorLinks)
      setProjectCostumeLinks(costumeLinks)

      const actorIds = Array.from(new Set(actorLinks.map((l) => l.actor_id)))
      const costumeIds = Array.from(new Set(costumeLinks.map((l) => l.costume_id)))

      const [actors, costumes] = await Promise.all([
        Promise.all(
          actorIds.map((id) =>
            StudioEntitiesApi.get('actor', id)
              .then((r) => (r.data ?? null) as ActorLike | null)
              .catch(() => null),
          ),
        ),
        Promise.all(
          costumeIds.map((id) =>
            StudioEntitiesApi.get('costume', id)
              .then((r) => (r.data ?? null) as CostumeLike | null)
              .catch(() => null),
          ),
        ),
      ])

      const nextActors: Record<string, ActorLike> = {}
      actors.filter(Boolean).forEach((a) => {
        nextActors[(a as ActorLike).id] = a as ActorLike
      })
      const nextCostumes: Record<string, CostumeLike> = {}
      costumes.filter(Boolean).forEach((c) => {
        nextCostumes[(c as CostumeLike).id] = c as CostumeLike
      })
      setActorsById(nextActors)
      setCostumesById(nextCostumes)
    } catch {
      message.error('加载项目关联演员/服装失败')
      setProjectActorLinks([])
      setProjectCostumeLinks([])
      setActorsById({})
      setCostumesById({})
    } finally {
      setLoadingLinks(false)
    }
  }

  useEffect(() => {
    void loadProjectLinks()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    void (async () => {
      try {
        const res = await StudioProjectsService.getProjectApiV1StudioProjectsProjectIdGet({ projectId })
        const nextVisual = (res.data?.visual_style as ProjectVisualStyleChoice | undefined) ?? (defaultVisualStyle as ProjectVisualStyleChoice)
        const nextStyle = (res.data?.style as string | undefined) ?? getDefaultStyle(nextVisual)
        setProjectVisualStyle(nextVisual)
        setProjectStyle(nextStyle)
      } catch {
        // ignore: fallback to default
      }
    })()
  }, [defaultVisualStyle, getDefaultStyle, projectId])

  const handleCreateRole = async () => {
    if (!projectId) return
    const name = formName.trim()
    if (!name) {
      message.warning('请输入角色名称')
      return
    }
    setCreating(true)
    try {
      const createRes = await StudioEntitiesApi.create('character', {
        id: newId('char'),
        project_id: projectId,
        chapter_id: pendingShotLinkChapterId,
        shot_id: pendingShotLinkShotId,
        name,
        description: formDesc.trim() || undefined,
        visual_style: formVisualStyle || '现实',
        style: formStyle,
        actor_id: formActorId ?? null,
        costume_id: formCostumeId ?? null,
      })
      const charId = (createRes.data as { id?: string } | undefined)?.id
      if (charId && pendingShotLinkShotId) {
        notifyShotAssetCreatedAndLinked({
          projectId,
          chapterId: pendingShotLinkChapterId,
          shotId: pendingShotLinkShotId,
          assetId: charId,
          assetName: name,
        })
      }
      message.success('角色创建成功')
      setCreateOpen(false)
      setFormName('')
      setFormDesc('')
      setFormActorId(undefined)
      setFormCostumeId(undefined)
      setFormVisualStyle(projectVisualStyle)
      setFormStyle(projectStyle)
      setPendingShotLinkShotId(null)
      setPendingShotLinkChapterId(null)
      await refresh()
    } catch {
      message.error('创建失败')
      setPendingShotLinkShotId(null)
      setPendingShotLinkChapterId(null)
    } finally {
      setCreating(false)
    }
  }

  const currentCharacterIds = useMemo(() => new Set(characters.map((c) => c.id)), [characters])

  // 加载用户全部角色资产（由 availableLibraryCharacters memo 过滤掉已关联的）
  const loadLibraryCharacters = async (searchQuery?: string) => {
    setLibraryLoading(true)
    try {
      const q = (searchQuery !== undefined ? searchQuery : librarySearch).trim()
      const res = await StudioEntitiesApi.list('character', {
        q: q ? q : null,
        order: 'updated_at',
        isDesc: true,
        page: 1,
        pageSize: 100,
      })
      setLibraryCharacters((res.data?.items ?? []) as CharacterLike[])
    } catch {
      message.error('加载角色资产库失败')
      setLibraryCharacters([])
    } finally {
      setLibraryLoading(false)
    }
  }

  useEffect(() => {
    if (linkModalOpen) void loadLibraryCharacters('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkModalOpen])

  // 关联角色到项目（创建 ProjectCharacterLink）
  const handleLinkCharacter = async (character: CharacterLike) => {
    if (!projectId) return
    setLinkingId(character.id)
    try {
      await StudioShotLinksService.createProjectCharacterLinkApiV1StudioShotLinksCharacterPost({
        requestBody: { project_id: projectId, asset_id: character.id },
      })
      message.success(`已关联角色「${character.name}」到项目`)
      setLinkModalOpen(false)
      await refresh()
    } catch {
      message.error('关联失败')
    } finally {
      setLinkingId(null)
    }
  }

  const roleCards = useMemo(() => {
    return characters.map((c) => {
      const actor = actorsById[c.actor_id]
      const costume = c.costume_id ? costumesById[c.costume_id] : undefined
      return { c, actor, costume }
    })
  }, [actorsById, characters, costumesById])

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(12)
  const pagedRoleCards = useMemo(() => {
    const start = (page - 1) * pageSize
    return roleCards.slice(start, start + pageSize)
  }, [page, pageSize, roleCards])

  useEffect(() => {
    setPage(1)
  }, [roleCards.length])

  const actorOptions = useMemo(() => {
    return projectActorLinks.map((l) => {
      const a = actorsById[l.actor_id]
      const url = resolveAssetUrl(a?.thumbnail)
      return {
        value: l.actor_id,
        searchLabel: a?.name ?? l.actor_id,
        label: (
          <div className="flex items-center gap-2 min-w-0">
            {url ? (
              <img src={url} alt="" className="w-6 h-6 rounded object-cover shrink-0" />
            ) : (
              <div className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
                <UserOutlined />
              </div>
            )}
            <div className="min-w-0 truncate">{a?.name ?? l.actor_id}</div>
          </div>
        ),
      }
    })
  }, [actorsById, projectActorLinks])

  const costumeOptions = useMemo(() => {
    return projectCostumeLinks.map((l) => {
      const c = costumesById[l.costume_id]
      return { value: l.costume_id, label: c?.name ?? l.costume_id, searchLabel: c?.name ?? l.costume_id }
    })
  }, [costumesById, projectCostumeLinks])

  // 资产库中过滤掉已关联到本项目的角色
  const availableLibraryCharacters = useMemo(
    () => libraryCharacters.filter((c) => !currentCharacterIds.has(c.id)),
    [libraryCharacters, currentCharacterIds],
  )

  if (!projectId) {
    return null
  }

  return (
    <div className="h-full overflow-auto">
      <Card
        title="项目角色"
        extra={
          <Space>
            <Button type="primary" icon={<PlusOutlined />} loading={creatingBlank} onClick={handleCreateBlank}>
              新建
            </Button>
            <Button
              type="primary"
              icon={<LinkOutlined />}
              onClick={() => {
                setLibrarySearch('')
                setLinkModalOpen(true)
              }}
            >
              从资产库关联
            </Button>
            <Button icon={<PlusOutlined />} onClick={() => navigate('/assets?tab=character')}>
              前往资产管理
            </Button>
          </Space>
        }
      >
        {characters.length === 0 && !loading ? (
          <Empty
            description="暂无项目角色，可从资产库关联角色到本项目"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Space>
              <Button type="primary" icon={<PlusOutlined />} loading={creatingBlank} onClick={handleCreateBlank}>
                新建
              </Button>
            </Space>
          </Empty>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {pagedRoleCards.map(({ c, actor, costume }) => (
              <DisplayImageCard
                key={c.id}
                title={<div className="truncate">{c.name}</div>}
                imageUrl={resolveAssetUrl(c.thumbnail)}
                imageAlt={c.name}
                enablePreview
                extra={
                  <Space size="small">
                    <Button
                      type="default"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => {
                        if (!projectId) return
                        navigate(`/projects/${projectId}/roles/${c.id}/edit`)
                      }}
                    >
                      编辑
                    </Button>
                    <Button
                      size="small"
                      danger
                      onClick={() => {
                        Modal.confirm({
                          title: `取消关联角色「${c.name}」？`,
                          content: '取消关联后该角色将从本项目中移除（角色本身不会被删除）。',
                          okText: '取消关联',
                          cancelText: '取消',
                          okButtonProps: { danger: true },
                          onOk: async () => {
                            try {
                              const linksRes = await StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
                                entityType: 'character',
                                projectId: projectId ?? '',
                                chapterId: null,
                                shotId: null,
                                assetId: c.id,
                                order: null,
                                isDesc: false,
                                page: 1,
                                pageSize: 1,
                              })
                              const link = linksRes.data?.items?.[0] as { id: number } | undefined
                              if (!link) { message.error('未找到关联记录'); return }
                              await StudioShotLinksService.deleteProjectCharacterLinkApiV1StudioShotLinksCharacterLinkIdDelete({ linkId: link.id })
                              message.success('已取消关联')
                              await refresh()
                            } catch {
                              message.error('操作失败')
                            }
                          },
                        })
                      }}
                    >
                      取消关联
                    </Button>
                  </Space>
                }
                meta={
                  <div className="space-y-1">
                    {c.description ? <div className="text-xs text-gray-600 line-clamp-2">{c.description}</div> : null}
                    <div className="text-xs text-gray-500 truncate">
                      演员：{actor?.name ?? c.actor_id}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      服装：{costume?.name ?? (c.costume_id ?? '—')}
                    </div>
                  </div>
                }
              />
            ))}
            </div>
            <div className="flex justify-end">
              <Pagination
                current={page}
                pageSize={pageSize}
                total={roleCards.length}
                showSizeChanger={false}
                showTotal={(t) => `共 ${t} 条`}
                onChange={(p, ps) => {
                  setPage(p)
                  setPageSize(ps)
                }}
              />
            </div>
          </div>
        )}
      </Card>

      <Modal
        title="新建角色"
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false)
          setPendingShotLinkShotId(null)
        }}
        onOk={handleCreateRole}
        okText="创建"
        cancelText="取消"
        confirmLoading={creating}
        width={560}
      >
        <div className="space-y-3">
          <div>
            <div className="text-sm text-gray-600 mb-1">角色名称</div>
            <Input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="例如：小雨" />
          </div>
          <div>
            <div className="text-sm text-gray-600 mb-1">描述（可选）</div>
            <Input.TextArea rows={3} value={formDesc} onChange={(e) => setFormDesc(e.target.value)} />
          </div>
          <div>
            <ProjectVisualStyleAndStyleFields
              visual_style={formVisualStyle}
              style={formStyle}
              options={projectStyleOptions}
              onChange={(next) => {
                setFormVisualStyle(next.visual_style)
                setFormStyle(next.style)
              }}
            />
          </div>
          <div>
            <div className="text-sm text-gray-600 mb-1">关联演员（可选）</div>
            <Select
              className="w-full"
              allowClear
              placeholder="可选择当前项目已关联的演员"
              loading={loadingLinks}
              value={formActorId}
              onChange={(v) => setFormActorId(v)}
              options={actorOptions}
              showSearch
              optionFilterProp="searchLabel"
              filterOption={(input, option) => String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())}
            />
          </div>
          <div>
            <div className="text-sm text-gray-600 mb-1">关联服装（可选）</div>
            <Select
              className="w-full"
              allowClear
              placeholder="选择当前项目已关联的服装"
              loading={loadingLinks}
              value={formCostumeId}
              onChange={(v) => setFormCostumeId(v)}
              options={costumeOptions}
              showSearch
              optionFilterProp="searchLabel"
              filterOption={(input, option) => String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())}
            />
          </div>
        </div>
      </Modal>

      {/* 从资产库关联角色弹窗 */}
      <Modal
        title="从资产库关联角色"
        open={linkModalOpen}
        onCancel={() => setLinkModalOpen(false)}
        footer={null}
        width={560}
      >
        <div className="mb-3">
          <Input.Search
            placeholder="搜索角色名称"
            allowClear
            value={librarySearch}
            onChange={(e) => setLibrarySearch(e.target.value)}
            onSearch={(value) => loadLibraryCharacters(value)}
          />
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          {libraryLoading ? (
            <div className="py-8 text-center text-gray-500">加载中...</div>
          ) : availableLibraryCharacters.length === 0 ? (
            <Empty
              description={
                libraryCharacters.length === 0
                  ? '暂无可关联的角色，请先在资产管理中创建角色'
                  : '当前项目已关联全部搜索结果'
              }
            />
          ) : (
            <div className="space-y-2">
              {availableLibraryCharacters.map((character) => {
                const thumbUrl = resolveAssetUrl(character.thumbnail)
                return (
                  <div
                    key={character.id}
                    className="flex items-center justify-between gap-3 rounded border border-gray-200 p-2 hover:bg-gray-50"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {thumbUrl ? (
                        <img src={thumbUrl} alt="" className="w-10 h-10 rounded object-cover shrink-0" />
                      ) : (
                        <div className="w-10 h-10 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
                          <UserOutlined />
                        </div>
                      )}
                      <div className="min-w-0">
                        <div className="font-medium truncate">{character.name}</div>
                        {character.description && (
                          <div className="text-xs text-gray-500 truncate">{character.description}</div>
                        )}
                      </div>
                    </div>
                    <Button
                      type="primary"
                      size="small"
                      loading={linkingId === character.id}
                      onClick={() => handleLinkCharacter(character)}
                    >
                      关联到项目
                    </Button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
