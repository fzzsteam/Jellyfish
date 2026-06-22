/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 管理员充值请求体。
 *
 * - `amount`: 非零整数；正数为充值，负数为扣减。
 * - `remark`: 备注；负充值（扣减）必填。
 */
export type PointsRechargeRequest = {
    /**
     * 充值金额，正数充值/负数扣减，不可为 0
     */
    amount: number;
    /**
     * 备注；负充值必填
     */
    remark?: (string | null);
};

