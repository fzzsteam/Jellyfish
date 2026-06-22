/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 用户积分账户摘要：余额/冻结/可用。
 *
 * 语义：`balance`=账户总额（含冻结），`frozen`=已冻结，`available=balance-frozen`。
 */
export type PointsSummaryRead = {
    /**
     * 积分余额（含冻结）
     */
    balance: number;
    /**
     * 已冻结积分
     */
    frozen: number;
    /**
     * 可用积分 = balance - frozen
     */
    available: number;
};

