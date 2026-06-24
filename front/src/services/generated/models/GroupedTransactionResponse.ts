/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OperationGroupRead } from './OperationGroupRead';
import type { Pagination } from './Pagination';
import type { PointTransactionRead } from './PointTransactionRead';
export type GroupedTransactionResponse = {
    items: Array<OperationGroupRead>;
    pagination: Pagination;
    simple_txns?: Array<PointTransactionRead>;
    simple_pagination?: (Pagination | null);
    matched_transaction_id?: (string | null);
};

