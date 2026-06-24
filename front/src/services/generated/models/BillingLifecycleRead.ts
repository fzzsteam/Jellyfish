/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BillingEventRead } from './BillingEventRead';
/**
 * 按 billing_id 聚合的单据生命周期。
 */
export type BillingLifecycleRead = {
    billing_id: string;
    business_type?: (string | null);
    model_id?: (string | null);
    /**
     * frozen/settled/refunded
     */
    status: string;
    frozen_amount?: number;
    net_amount?: number;
    remark?: (string | null);
    created_by?: (string | null);
    created_by_username?: (string | null);
    created_at?: (string | null);
    events?: Array<BillingEventRead>;
};

