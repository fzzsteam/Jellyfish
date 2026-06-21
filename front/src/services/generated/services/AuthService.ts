/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_AccessTokenRead_ } from '../models/ApiResponse_AccessTokenRead_';
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_TokenPairRead_ } from '../models/ApiResponse_TokenPairRead_';
import type { ApiResponse_UserRead_ } from '../models/ApiResponse_UserRead_';
import type { ChangePasswordRequest } from '../models/ChangePasswordRequest';
import type { LoginRequest } from '../models/LoginRequest';
import type { RefreshRequest } from '../models/RefreshRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AuthService {
    /**
     * 登录
     * 用户名密码登录，返回 access_token 和 refresh_token。
     * @returns ApiResponse_TokenPairRead_ Successful Response
     * @throws ApiError
     */
    public static loginApiV1AuthLoginPost({
        requestBody,
    }: {
        requestBody: LoginRequest,
    }): CancelablePromise<ApiResponse_TokenPairRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 刷新 access token
     * 使用 refresh_token 换取新的 access_token。
     * @returns ApiResponse_AccessTokenRead_ Successful Response
     * @throws ApiError
     */
    public static refreshApiV1AuthRefreshPost({
        requestBody,
    }: {
        requestBody: RefreshRequest,
    }): CancelablePromise<ApiResponse_AccessTokenRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/refresh',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取当前用户信息
     * 获取当前登录用户的基本信息。
     * @returns ApiResponse_UserRead_ Successful Response
     * @throws ApiError
     */
    public static getMeApiV1AuthMeGet({
        authorization,
    }: {
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_UserRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/me',
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改当前用户密码
     * 当前用户校验旧密码后修改自己的密码；成功后已签发的 token 立即失效。
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static changePasswordApiV1AuthChangePasswordPost({
        requestBody,
        authorization,
    }: {
        requestBody: ChangePasswordRequest,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/change-password',
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
