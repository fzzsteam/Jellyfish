/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_list_UserProjectBrief__ } from '../models/ApiResponse_list_UserProjectBrief__';
import type { ApiResponse_PaginatedData_UserAdminRead__ } from '../models/ApiResponse_PaginatedData_UserAdminRead__';
import type { ApiResponse_ResetPasswordRead_ } from '../models/ApiResponse_ResetPasswordRead_';
import type { ApiResponse_UserAdminRead_ } from '../models/ApiResponse_UserAdminRead_';
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
}
