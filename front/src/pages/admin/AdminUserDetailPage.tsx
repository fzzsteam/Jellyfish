import { useEffect, useState } from 'react'
import type React from 'react'
import {
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  message,
} from 'antd'
import { useParams } from 'react-router-dom'
import { PointsAccountCard } from '../../components/points/PointsAccountCard'
import { PointTransactionTable } from '../../components/points/PointTransactionTable'
import { SimplePointTransactionTable } from '../../components/points/SimplePointTransactionTable'
import { AdminService } from '../../services/generated'
import type {
  OperationGroupRead,
  PointsSummaryRead,
  PointTransactionRead,
  UserAdminRead,
  UserProjectBrief,
} from '../../services/generated'

/** 充值快捷金额选项。 */
const RECHARGE_PRESETS = [100, 500, 1000, 5000]

/**
 * 管理员用户详情页：展示用户信息、积分账户、积分充值与积分流水，
 * 以及该用户的项目列表。积分相关数据通过 generated AdminService 拉取。
 */
const AdminUserDetailPage: React.FC = () => {
  const { id = '' } = useParams()
  const [user, setUser] = useState<UserAdminRead | null>(null)
  const [projects, setProjects] = useState<UserProjectBrief[]>([])
  const [points, setPoints] = useState<PointsSummaryRead | null>(null)
  const [groupedData, setGroupedData] = useState<OperationGroupRead[]>([])
  const [groupedTotal, setGroupedTotal] = useState(0)
  const [groupedLoading, setGroupedLoading] = useState(false)
  const [groupedPage, setGroupedPage] = useState(1)
  const [groupedPageSize, setGroupedPageSize] = useState(10)
  // 三种 ID 搜索类型与值，以及搜索命中后的行高亮状态。
  const [searchIdType, setSearchIdType] = useState<'cascade_group_id' | 'billing_id' | 'transaction_id'>('cascade_group_id')
  const [searchIdValue, setSearchIdValue] = useState<string | undefined>(undefined)
  const [highlightTransactionId, setHighlightTransactionId] = useState<string | undefined>(undefined)
  const [simpleTxns, setSimpleTxns] = useState<PointTransactionRead[]>([])
  // 充值/调整流水的独立分页状态，与操作记录分页互不影响。
  const [simplePage, setSimplePage] = useState(1)
  const [simplePageSize, setSimplePageSize] = useState(10)
  const [simpleTotal, setSimpleTotal] = useState(0)
  const [recharging, setRecharging] = useState(false)
  const [rechargeOpen, setRechargeOpen] = useState(false)
  const [resetPwdOpen, setResetPwdOpen] = useState(false)
  const [resetPwdLoading, setResetPwdLoading] = useState(false)
  const [pwdForm] = Form.useForm()
  const [rechargeForm] = Form.useForm()

  /** 一次性加载用户基础信息 + 项目 + 积分摘要（首屏）。 */
  const load = async () => {
    try {
      const [u, p, pts] = await Promise.all([
        AdminService.getUserApiV1AdminUsersUserIdGet({ userId: id }),
        AdminService.listUserProjectsApiV1AdminUsersUserIdProjectsGet({ userId: id }),
        AdminService.getUserPointsApiV1AdminUsersUserIdPointsGet({ userId: id }).catch(() => null),
      ])
      setUser(u.data ?? null)
      setProjects(p.data ?? [])
      setPoints(pts?.data ?? null)
    } catch {
      message.error('加载失败')
    }
  }

  /**
   * 加载按操作分组流水，按页拉取。
   * 支持三种 ID 过滤：操作ID(cascade_group_id)、账单ID(billing_id)、流水ID(transaction_id)。
   * 当按 transaction_id 搜索时，后端返回 matched_transaction_id 用于高亮命中行。
   * simpleP/simplePs 控制充值/调整 Tab 的独立分页，与操作记录分页解耦。
   */
  const loadGrouped = async (
    page: number,
    pageSize: number,
    idType?: 'cascade_group_id' | 'billing_id' | 'transaction_id',
    idValue?: string,
    simpleP: number = 1,
    simplePs: number = 10,
  ) => {
    setGroupedLoading(true)
    try {
      const res = await AdminService.listUserPointsTransactionsGroupedApiV1AdminUsersUserIdPointsTransactionsGroupedGet({
        userId: id,
        page,
        pageSize,
        cascadeGroupId: idType === 'cascade_group_id' ? idValue : undefined,
        billingId: idType === 'billing_id' ? idValue : undefined,
        transactionId: idType === 'transaction_id' ? idValue : undefined,
        simplePage: simpleP,
        simplePageSize: simplePs,
      })
      setGroupedData(res.data?.items ?? [])
      setGroupedTotal(res.data?.pagination?.total ?? 0)
      setHighlightTransactionId(res.data?.matched_transaction_id ?? undefined)
      setSimpleTxns(res.data?.simple_txns ?? [])
      setSimpleTotal(res.data?.simple_pagination?.total ?? 0)
    } catch {
      message.error('分组流水加载失败')
    } finally {
      setGroupedLoading(false)
    }
  }

  useEffect(() => {
    if (id) {
      void load()
      void loadGrouped(1, groupedPageSize)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  /** 提交密码重置。 */
  const handleResetPassword = async () => {
    const { password } = await pwdForm.validateFields()
    setResetPwdLoading(true)
    try {
      await AdminService.updateUserApiV1AdminUsersUserIdPatch({ userId: id, requestBody: { password } })
      message.success('密码已重置，该用户需重新登录')
      setResetPwdOpen(false)
      pwdForm.resetFields()
    } catch {
      message.error('重置失败')
    } finally {
      setResetPwdLoading(false)
    }
  }

  /** 提交积分充值：校验由 Form rules 承担，此处直接调接口。 */
  const handleRecharge = async () => {
    const values = await rechargeForm.validateFields()
    const amount = Number(values.amount)
    setRecharging(true)
    try {
      await AdminService.rechargeUserPointsApiV1AdminUsersUserIdPointsRechargePost({
        userId: id,
        requestBody: { amount, remark: values.remark?.trim() || null },
      })
      message.success(amount > 0 ? '充值成功' : '扣减成功')
      setRechargeOpen(false)
      rechargeForm.resetFields()
      // 充值后刷新摘要与分组流水，两个 Tab 均回到第 1 页。
      const pts = await AdminService.getUserPointsApiV1AdminUsersUserIdPointsGet({ userId: id })
      setPoints(pts.data ?? null)
      setGroupedPage(1)
      setSimplePage(1)
      await loadGrouped(1, groupedPageSize)
    } catch {
      message.error('充值失败')
    } finally {
      setRecharging(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* 用户信息 + 积分账户，header 右侧放操作按钮 */}
      <Card
        title="用户信息"
        extra={
          <div className="flex gap-2">
            <Button onClick={() => setResetPwdOpen(true)}>重置密码</Button>
            <Button type="primary" onClick={() => setRechargeOpen(true)}>充值积分</Button>
          </div>
        }
      >
        <div className="grid grid-cols-2 gap-6">
          <Descriptions column={1}>
            <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
            <Descriptions.Item label="角色">
              {user?.is_admin ? <Tag color="gold">管理员</Tag> : <Tag>成员</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {user?.is_active ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>}
            </Descriptions.Item>
          </Descriptions>
          <PointsAccountCard summary={points ?? null} />
        </div>
      </Card>

      {/* 积分流水 + 关联项目 Tab */}
      <Card>
        <Tabs
          defaultActiveKey="transactions"
          items={[
            {
              key: 'transactions',
              label: '积分流水',
              children: (
                <Tabs
                  defaultActiveKey="operations"
                  size="small"
                  items={[
                    {
                      key: 'operations',
                      label: '操作记录',
                      children: (
                        <div>
                          {/* 三种 ID 搜索：操作ID / 账单ID / 流水ID */}
                          <div className="mb-3">
                            <Space>
                              <Select<'cascade_group_id' | 'billing_id' | 'transaction_id'>
                                size="small"
                                value={searchIdType}
                                style={{ width: 88 }}
                                options={[
                                  { label: '操作ID', value: 'cascade_group_id' },
                                  { label: '账单ID', value: 'billing_id' },
                                  { label: '流水ID', value: 'transaction_id' },
                                ]}
                                onChange={(v) => {
                                  setSearchIdType(v)
                                  setSearchIdValue(undefined)
                                  setHighlightTransactionId(undefined)
                                }}
                              />
                              <Input.Search
                                allowClear
                                placeholder="输入搜索值"
                                size="small"
                                style={{ width: 200 }}
                                value={searchIdValue}
                                onChange={(e) => setSearchIdValue(e.target.value || undefined)}
                                onSearch={(v) => {
                                  const val = v.trim() || undefined
                                  setSearchIdValue(val)
                                  setGroupedPage(1)
                                  void loadGrouped(1, groupedPageSize, searchIdType, val, simplePage, simplePageSize)
                                  if (!val) setHighlightTransactionId(undefined)
                                }}
                              />
                            </Space>
                          </div>
                          <PointTransactionTable
                            dataSource={groupedData}
                            loading={groupedLoading}
                            total={groupedTotal}
                            page={groupedPage}
                            pageSize={groupedPageSize}
                            highlightTransactionId={highlightTransactionId}
                            highlightBillingId={searchIdType === 'billing_id' ? searchIdValue : undefined}
                            onChange={(page, pageSize) => {
                              setGroupedPage(page)
                              setGroupedPageSize(pageSize)
                              void loadGrouped(page, pageSize, searchIdType, searchIdValue, simplePage, simplePageSize)
                            }}
                          />
                        </div>
                      ),
                    },
                    {
                      key: 'simple',
                      label: '充值',
                      children: (
                        <SimplePointTransactionTable
                          dataSource={simpleTxns}
                          page={simplePage}
                          pageSize={simplePageSize}
                          total={simpleTotal}
                          onChange={(p, ps) => {
                            setSimplePage(p)
                            setSimplePageSize(ps)
                            void loadGrouped(groupedPage, groupedPageSize, searchIdType, searchIdValue, p, ps)
                          }}
                        />
                      ),
                    },
                  ]}
                />
              ),
            },
            {
              key: 'projects',
              label: `关联项目${projects.length ? `（${projects.length}）` : ''}`,
              children: (
                <Table
                  rowKey="id"
                  dataSource={projects}
                  pagination={false}
                  size="small"
                  columns={[
                    { title: '项目名', dataIndex: 'name' },
                    { title: '项目 ID', dataIndex: 'id', ellipsis: true },
                  ]}
                />
              ),
            },
          ]}
        />
      </Card>

      {/* 充值积分弹窗 */}
      <Modal
        title={`充值积分 — ${user?.username ?? ''}`}
        open={rechargeOpen}
        onOk={() => void handleRecharge()}
        onCancel={() => { setRechargeOpen(false); rechargeForm.resetFields() }}
        okText="确认"
        cancelText="取消"
        confirmLoading={recharging}
        destroyOnClose
      >
        <Form form={rechargeForm} layout="vertical" className="mt-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-sm text-gray-500">快捷：</span>
            {RECHARGE_PRESETS.map((preset) => (
              <Button
                key={preset}
                size="small"
                onClick={() => rechargeForm.setFieldValue('amount', preset)}
              >
                +{preset}
              </Button>
            ))}
          </div>
          <Form.Item
            name="amount"
            label="积分数量（正数充值，负数扣减）"
            rules={[
              { required: true, message: '请输入积分数量' },
              { type: 'integer', message: '请输入整数' },
              {
                validator: (_, value) => value !== 0 ? Promise.resolve() : Promise.reject(new Error('不能为 0')),
              },
            ]}
          >
            <InputNumber style={{ width: '100%' }} placeholder="如：100 或 -50" />
          </Form.Item>
          <Form.Item
            name="remark"
            label="备注"
            rules={[
              ({ getFieldValue }) => ({
                validator(_, value) {
                  const amount = getFieldValue('amount') as number
                  if (amount < 0 && !value?.trim()) {
                    return Promise.reject(new Error('扣减积分必须填写备注'))
                  }
                  return Promise.resolve()
                },
              }),
            ]}
          >
            <Input placeholder="说明充值/扣减原因（扣减时必填）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置密码弹窗 */}
      <Modal
        title={`重置密码 — ${user?.username ?? ''}`}
        open={resetPwdOpen}
        onOk={() => void handleResetPassword()}
        onCancel={() => { setResetPwdOpen(false); pwdForm.resetFields() }}
        okText="确认重置"
        cancelText="取消"
        confirmLoading={resetPwdLoading}
        destroyOnClose
      >
        <Form form={pwdForm} layout="vertical" className="mt-4">
          <Form.Item
            name="password"
            label="新密码"
            rules={[{ required: true, min: 6, message: '至少 6 位' }]}
          >
            <Input.Password placeholder="请输入新密码（至少 6 位）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default AdminUserDetailPage
