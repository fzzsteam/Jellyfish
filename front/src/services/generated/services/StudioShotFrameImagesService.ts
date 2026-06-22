/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_ShotFrameImageRead__ } from '../models/ApiResponse_PaginatedData_ShotFrameImageRead__';
import type { ApiResponse_ShotFrameImageRead_ } from '../models/ApiResponse_ShotFrameImageRead_';
import type { ShotFrameImageCreate } from '../models/ShotFrameImageCreate';
import type { ShotFrameImageUpdate } from '../models/ShotFrameImageUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioShotFrameImagesService {
    /**
     * 镜头分镜帧图片列表（分页）
     * @returns ApiResponse_PaginatedData_ShotFrameImageRead__ Successful Response
     * @throws ApiError
     */
    public static listShotFrameImagesApiV1StudioShotFrameImagesGet({
        shotDetailId,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
        authorization,
    }: {
        /**
         * 按镜头细节过滤
         */
        shotDetailId?: (string | null),
        order?: (string | null),
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_ShotFrameImageRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shot-frame-images',
            headers: {
                'authorization': authorization,
            },
            query: {
                'shot_detail_id': shotDetailId,
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
     * 创建镜头分镜帧图片
     * @returns ApiResponse_ShotFrameImageRead_ Successful Response
     * @throws ApiError
     */
    public static createShotFrameImageApiV1StudioShotFrameImagesPost({
        requestBody,
        authorization,
    }: {
        requestBody: ShotFrameImageCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ShotFrameImageRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/shot-frame-images',
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
     * 更新镜头分镜帧图片
     * @returns ApiResponse_ShotFrameImageRead_ Successful Response
     * @throws ApiError
     */
    public static updateShotFrameImageApiV1StudioShotFrameImagesImageIdPatch({
        imageId,
        requestBody,
        authorization,
    }: {
        imageId: number,
        requestBody: ShotFrameImageUpdate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ShotFrameImageRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/shot-frame-images/{image_id}',
            path: {
                'image_id': imageId,
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
     * 删除镜头分镜帧图片
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteShotFrameImageApiV1StudioShotFrameImagesImageIdDelete({
        imageId,
        authorization,
    }: {
        imageId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/shot-frame-images/{image_id}',
            path: {
                'image_id': imageId,
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
