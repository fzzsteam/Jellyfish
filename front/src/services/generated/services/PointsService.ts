/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_GroupedTransactionResponse_ } from '../models/ApiResponse_GroupedTransactionResponse_';
import type { ApiResponse_PaginatedData_PointTransactionRead__ } from '../models/ApiResponse_PaginatedData_PointTransactionRead__';
import type { ApiResponse_PointsQuoteResponse_ } from '../models/ApiResponse_PointsQuoteResponse_';
import type { ApiResponse_PointsSummaryRead_ } from '../models/ApiResponse_PointsSummaryRead_';
import type { PointsQuoteRequest } from '../models/PointsQuoteRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class PointsService {
    /**
     * 当前用户积分摘要
     * 返回当前用户余额/冻结/可用额度（纯读取，首次访问自动初始化为 0）。
     * @returns ApiResponse_PointsSummaryRead_ Successful Response
     * @throws ApiError
     */
    public static getMyPointsApiV1PointsMeGet({
        authorization,
    }: {
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PointsSummaryRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/points/me',
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 当前用户积分流水
     * 分页查询当前用户积分流水，按 created_at 倒序。
     *
     * 非法 `type`（非 recharge/freeze/consume/unfreeze）→ 422。
     * @returns ApiResponse_PaginatedData_PointTransactionRead__ Successful Response
     * @throws ApiError
     */
    public static listMyTransactionsApiV1PointsTransactionsGet({
        type,
        businessType,
        billingId,
        id,
        page = 1,
        pageSize = 20,
        authorization,
    }: {
        /**
         * 按流水类型过滤：recharge/freeze/consume/unfreeze
         */
        type?: (string | null),
        /**
         * 按业务类型过滤
         */
        businessType?: (string | null),
        /**
         * 按计费单据 ID 过滤
         */
        billingId?: (string | null),
        /**
         * 按流水 ID 精确搜索
         */
        id?: (string | null),
        page?: number,
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_PointTransactionRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/points/transactions',
            headers: {
                'authorization': authorization,
            },
            query: {
                'type': type,
                'business_type': businessType,
                'billing_id': billingId,
                'id': id,
                'page': page,
                'page_size': pageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 按操作组聚合的积分流水
     * 按 cascade_group_id 聚合展示流水。同一操作级联的多个 billing_id 归为一组。
     *
     * 支持三种 ID 搜索：
     * - cascade_group_id：直接按操作组 ID 过滤
     * - billing_id：先解析到所属操作组，再返回该组数据
     * - transaction_id：先解析到所属操作组，再返回该组数据，并在 matched_transaction_id 中标记命中流水 ID
     * simple_page / simple_page_size 用于充值/调整记录的独立分页。
     * @returns ApiResponse_GroupedTransactionResponse_ Successful Response
     * @throws ApiError
     */
    public static listGroupedTransactionsApiV1PointsTransactionsGroupedGet({
        page = 1,
        pageSize = 20,
        cascadeGroupId,
        billingId,
        transactionId,
        simplePage = 1,
        simplePageSize = 20,
        authorization,
    }: {
        page?: number,
        pageSize?: number,
        /**
         * 按操作ID精确搜索
         */
        cascadeGroupId?: (string | null),
        /**
         * 按账单ID搜索，返回所属操作组
         */
        billingId?: (string | null),
        /**
         * 按流水ID搜索，返回所属操作组
         */
        transactionId?: (string | null),
        /**
         * 充值/调整记录分页页码
         */
        simplePage?: number,
        /**
         * 充值/调整记录每页数量
         */
        simplePageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_GroupedTransactionResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/points/transactions/grouped',
            headers: {
                'authorization': authorization,
            },
            query: {
                'page': page,
                'page_size': pageSize,
                'cascade_group_id': cascadeGroupId,
                'billing_id': billingId,
                'transaction_id': transactionId,
                'simple_page': simplePage,
                'simple_page_size': simplePageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 积分试算
     * 试算本次生成所需积分并签发短期 quote_token。
     *
     * - 不支持的视频分辨率 → 400。
     * - 用户未配置默认模型 → 503（配置错误，由通用处理器兜底）。
     * @returns ApiResponse_PointsQuoteResponse_ Successful Response
     * @throws ApiError
     */
    public static quoteMyPointsApiV1PointsQuotePost({
        requestBody,
        authorization,
    }: {
        requestBody: PointsQuoteRequest,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PointsQuoteResponse_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/points/quote',
            headers: {
                'authorization': authorization,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
