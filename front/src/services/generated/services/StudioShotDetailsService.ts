/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_ShotDetailRead__ } from '../models/ApiResponse_PaginatedData_ShotDetailRead__';
import type { ApiResponse_ShotDetailRead_ } from '../models/ApiResponse_ShotDetailRead_';
import type { ShotDetailCreate } from '../models/ShotDetailCreate';
import type { ShotDetailUpdate } from '../models/ShotDetailUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioShotDetailsService {
    /**
     * 镜头细节列表（分页）
     * @returns ApiResponse_PaginatedData_ShotDetailRead__ Successful Response
     * @throws ApiError
     */
    public static listShotDetailsApiV1StudioShotDetailsGet({
        shotId,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
        authorization,
    }: {
        /**
         * 按镜头过滤（id 同 shot_id）
         */
        shotId?: (string | null),
        order?: (string | null),
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_ShotDetailRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shot-details',
            headers: {
                'authorization': authorization,
            },
            query: {
                'shot_id': shotId,
                'order': order,
                'is_desc': isDesc,
                'page': page,
                'page_size': pageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创建镜头细节
     * @returns ApiResponse_ShotDetailRead_ Successful Response
     * @throws ApiError
     */
    public static createShotDetailApiV1StudioShotDetailsPost({
        requestBody,
        authorization,
    }: {
        requestBody: ShotDetailCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ShotDetailRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/shot-details',
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
     * 获取镜头细节
     * @returns ApiResponse_ShotDetailRead_ Successful Response
     * @throws ApiError
     */
    public static getShotDetailApiV1StudioShotDetailsShotIdGet({
        shotId,
        authorization,
    }: {
        shotId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ShotDetailRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shot-details/{shot_id}',
            path: {
                'shot_id': shotId,
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
     * 更新镜头细节
     * @returns ApiResponse_ShotDetailRead_ Successful Response
     * @throws ApiError
     */
    public static updateShotDetailApiV1StudioShotDetailsShotIdPatch({
        shotId,
        requestBody,
        authorization,
    }: {
        shotId: string,
        requestBody: ShotDetailUpdate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ShotDetailRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/shot-details/{shot_id}',
            path: {
                'shot_id': shotId,
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
     * 删除镜头细节
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteShotDetailApiV1StudioShotDetailsShotIdDelete({
        shotId,
        authorization,
    }: {
        shotId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/shot-details/{shot_id}',
            path: {
                'shot_id': shotId,
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
