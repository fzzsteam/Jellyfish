/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BillingLifecycleRead } from './BillingLifecycleRead';
/**
 * 按 cascade_group_id 聚合的操作组。
 */
export type OperationGroupRead = {
    cascade_group_id?: (string | null);
    business_type?: (string | null);
    created_at?: (string | null);
    total_net?: number;
    billings?: Array<BillingLifecycleRead>;
};

