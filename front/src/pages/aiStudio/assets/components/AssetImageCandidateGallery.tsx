import { DeleteOutlined } from '@ant-design/icons'
import { Button, Empty, Image, Popconfirm, Space, Tag, Typography } from 'antd'
import type { AssetImageCandidateRead } from '../../../../services/generated'

type Props = {
  candidates: AssetImageCandidateRead[]
  loading?: boolean
  adoptingId?: number | null
  deletingId?: number | null
  resolveFileUrl: (fileId: string) => string
  onAdopt: (candidate: AssetImageCandidateRead) => Promise<void>
  onDelete?: (candidate: AssetImageCandidateRead) => Promise<void>
}

function sourceLabel(sourceType: string): string {
  if (sourceType === 'upload') return '本地上传'
  if (sourceType === 'generation') return '生成结果'
  return sourceType || '候选图片'
}

export function AssetImageCandidateGallery({
  candidates,
  loading,
  adoptingId,
  deletingId,
  resolveFileUrl,
  onAdopt,
  onDelete,
}: Props) {
  if (!loading && candidates.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无候选图片" />
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
      {candidates.map((candidate) => {
        const adopted = Boolean(candidate.is_adopted)
        return (
          <div key={candidate.id} className="rounded border border-gray-200 p-3">
            <div className="flex aspect-video w-full items-center justify-center overflow-hidden rounded bg-gray-50">
              <Image
                src={resolveFileUrl(candidate.file_id)}
                alt={`candidate-${candidate.id}`}
                width="100%"
                height="100%"
                style={{ objectFit: 'contain' }}
              />
            </div>
            <Space direction="vertical" size={8} className="mt-3 w-full">
              <Space wrap>
                <Tag color={adopted ? 'green' : 'blue'}>{adopted ? '当前采用' : sourceLabel(candidate.source_type)}</Tag>
                <Typography.Text type="secondary">ID {candidate.id}</Typography.Text>
              </Space>
              <Space>
                <Button
                  type={adopted ? 'default' : 'primary'}
                  size="small"
                  disabled={adopted}
                  loading={adoptingId === candidate.id}
                  onClick={() => void onAdopt(candidate)}
                >
                  {adopted ? '已采用' : '设为当前图'}
                </Button>
                {onDelete ? (
                  <Popconfirm
                    title="删除候选关系"
                    description="只从候选池移除，不删除文件。"
                    okText="删除"
                    cancelText="取消"
                    disabled={adopted}
                    onConfirm={() => void onDelete(candidate)}
                  >
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      disabled={adopted}
                      loading={deletingId === candidate.id}
                    />
                  </Popconfirm>
                ) : null}
              </Space>
            </Space>
          </div>
        )
      })}
    </div>
  )
}
