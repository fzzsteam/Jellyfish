/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_list_UserProjectBrief__ } from '../models/ApiResponse_list_UserProjectBrief__';
import type { ApiResponse_PaginatedData_PointTransactionRead__ } from '../models/ApiResponse_PaginatedData_PointTransactionRead__';
import type { ApiResponse_PaginatedData_UserAdminRead__ } from '../models/ApiResponse_PaginatedData_UserAdminRead__';
import type { ApiResponse_PointsSummaryRead_ } from '../models/ApiResponse_PointsSummaryRead_';
import type { ApiResponse_PointTransactionRead_ } from '../models/ApiResponse_PointTransactionRead_';
import type { ApiResponse_ResetPasswordRead_ } from '../models/ApiResponse_ResetPasswordRead_';
import type { ApiResponse_UserAdminRead_ } from '../models/ApiResponse_UserAdminRead_';
import type { PointsRechargeRequest } from '../models/PointsRechargeRequest';
import type { UserCreate } from '../models/UserCreate';
import type { UserUpdate } from '../models/UserUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminService {
    /**
     * 用户列表
     * @returns ApiResponse_PaginatedData_UserAdminRead__ Successful Response
     * @throws ApiError
     */
    public static listUsersApiV1AdminUsersGet({
        page = 1,
        pageSize = 20,
        authorization,
    }: {
        page?: number,
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_UserAdminRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/users',
            headers: {
                'authorization': authorization,
            },
            query: {
                'page': page,
                'page_size': pageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创建用户
     * @returns ApiResponse_UserAdminRead_ Successful Response
     * @throws ApiError
     */
    public static createUserApiV1AdminUsersPost({
        requestBody,
        authorization,
    }: {
        requestBody: UserCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_UserAdminRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/users',
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
    /**
     * 用户详情
     * @returns ApiResponse_UserAdminRead_ Successful Response
     * @throws ApiError
     */
    public static getUserApiV1AdminUsersUserIdGet({
        userId,
        authorization,
    }: {
        userId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_UserAdminRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/users/{user_id}',
            path: {
                'user_id': userId,
            },
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改用户
     * @returns ApiResponse_UserAdminRead_ Successful Response
     * @throws ApiError
     */
    public static updateUserApiV1AdminUsersUserIdPatch({
        userId,
        requestBody,
        authorization,
    }: {
        userId: string,
        requestBody: UserUpdate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_UserAdminRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/admin/users/{user_id}',
            path: {
                'user_id': userId,
            },
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
    /**
     * 重置用户密码
     * 管理员重置目标用户密码；后端生成一次性临时密码并返回。
     *
     * 不允许重置自己（应通过自助改密接口）；目标用户不存在返回 404。
     * @returns ApiResponse_ResetPasswordRead_ Successful Response
     * @throws ApiError
     */
    public static resetPasswordApiV1AdminUsersUserIdResetPasswordPost({
        userId,
        authorization,
    }: {
        userId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ResetPasswordRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/users/{user_id}/reset-password',
            path: {
                'user_id': userId,
            },
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查看某用户的项目
     * @returns ApiResponse_list_UserProjectBrief__ Successful Response
     * @throws ApiError
     */
    public static listUserProjectsApiV1AdminUsersUserIdProjectsGet({
        userId,
        authorization,
    }: {
        userId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_list_UserProjectBrief__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/users/{user_id}/projects',
            path: {
                'user_id': userId,
            },
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查看某用户积分摘要
     * 返回目标用户余额/冻结/可用额度。
     * @returns ApiResponse_PointsSummaryRead_ Successful Response
     * @throws ApiError
     */
    public static getUserPointsApiV1AdminUsersUserIdPointsGet({
        userId,
        authorization,
    }: {
        userId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PointsSummaryRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/users/{user_id}/points',
            path: {
                'user_id': userId,
            },
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查看某用户积分流水
     * 分页查询目标用户积分流水，按 created_at 倒序。
     *
     * 非法 `type`（非 recharge/freeze/consume/unfreeze）→ 422。
     * @returns ApiResponse_PaginatedData_PointTransactionRead__ Successful Response
     * @throws ApiError
     */
    public static listUserPointsTransactionsApiV1AdminUsersUserIdPointsTransactionsGet({
        userId,
        type,
        businessType,
        billingId,
        page = 1,
        pageSize = 20,
        authorization,
    }: {
        userId: string,
        /**
         * 流水类型
         */
        type?: (string | null),
        /**
         * 业务类型
         */
        businessType?: (string | null),
        /**
         * 计费单据 ID
         */
        billingId?: (string | null),
        page?: number,
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_PointTransactionRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/users/{user_id}/points/transactions',
            path: {
                'user_id': userId,
            },
            headers: {
                'authorization': authorization,
            },
            query: {
                'type': type,
                'business_type': businessType,
                'billing_id': billingId,
                'page': page,
                'page_size': pageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 管理员充值/扣减用户积分
     * 对目标用户积分账户充值（正）或扣减（负）。
     *
     * - 负充值必须带 remark（否则 ledger 抛 ValueError → 400）。
     * - 负充值不得侵蚀冻结额（否则抛 InsufficientPointsError → PointsDomainError 402）。
     * @returns ApiResponse_PointTransactionRead_ Successful Response
     * @throws ApiError
     */
    public static rechargeUserPointsApiV1AdminUsersUserIdPointsRechargePost({
        userId,
        requestBody,
        authorization,
    }: {
        userId: string,
        requestBody: PointsRechargeRequest,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PointTransactionRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/users/{user_id}/points/recharge',
            path: {
                'user_id': userId,
            },
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
