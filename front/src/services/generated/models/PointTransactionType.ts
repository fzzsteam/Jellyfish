/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 积分流水类型：覆盖积分账户的全部状态流转动作。
 *
 * - recharge: 充值（余额增加）
 * - freeze: 冻结（下单时预占，余额不变，冻结额增加）
 * - consume: 扣减（任务成功后从冻结额结算扣出，余额与冻结额同步减少）
 * - unfreeze: 解冻（任务失败/取消时释放冻结额）
 */
export type PointTransactionType = 'recharge' | 'freeze' | 'consume' | 'unfreeze';
