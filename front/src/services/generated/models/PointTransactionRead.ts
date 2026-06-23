/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PointTransactionType } from './PointTransactionType';
/**
 * 积分流水只读 DTO。
 *
 * `type` 直接取 ORM 枚举值字符串（recharge/freeze/consume/unfreeze），
 * `pricing_snapshot` 透传 JSON 快照用于历史对账。
 */
export type PointTransactionRead = {
    /**
     * 流水 ID
     */
    id: string;
    /**
     * 归属用户 ID
     */
    user_id: string;
    /**
     * 流水类型
     */
    type: PointTransactionType;
    /**
     * 本次变更积分数量（符号随类型）
     */
    amount: number;
    /**
     * 变更后余额
     */
    balance_after: number;
    /**
     * 变更后冻结额
     */
    frozen_after: number;
    /**
     * 来源标签
     */
    source: string;
    /**
     * 计费单据 ID
     */
    billing_id?: (string | null);
    /**
     * 业务类型
     */
    business_type?: (string | null);
    /**
     * 业务实体 ID
     */
    business_id?: (string | null);
    /**
     * 涉及的模型 ID
     */
    model_id?: (string | null);
    /**
     * 计价快照
     */
    pricing_snapshot?: (Record<string, any> | null);
    /**
     * 级联分组键
     */
    cascade_group_id?: (string | null);
    /**
     * 备注
     */
    remark?: (string | null);
    /**
     * 操作人 ID
     */
    created_by?: (string | null);
    /**
     * 操作人用户名
     */
    created_by_username?: (string | null);
    /**
     * 流水发生时间
     */
    created_at: string;
};

