/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PointTransactionType } from './PointTransactionType';
/**
 * 同 billing_id 生命周期内的一条事件（freeze/consume/unfreeze 明细）。
 */
export type BillingEventRead = {
    id: string;
    type: PointTransactionType;
    amount: number;
    created_at?: (string | null);
    balance_after?: (number | null);
    frozen_after?: (number | null);
};

