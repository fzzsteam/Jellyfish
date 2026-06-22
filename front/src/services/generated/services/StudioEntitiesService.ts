/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_AssetImageCandidateRead_ } from '../models/ApiResponse_AssetImageCandidateRead_';
import type { ApiResponse_dict_str__Any__ } from '../models/ApiResponse_dict_str__Any__';
import type { ApiResponse_EntityNameExistenceCheckResponse_ } from '../models/ApiResponse_EntityNameExistenceCheckResponse_';
import type { ApiResponse_list_AssetImageCandidateRead__ } from '../models/ApiResponse_list_AssetImageCandidateRead__';
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_dict_str__Any___ } from '../models/ApiResponse_PaginatedData_dict_str__Any___';
import type { AssetImageCandidateAttachRequest } from '../models/AssetImageCandidateAttachRequest';
import type { EntityNameExistenceCheckRequest } from '../models/EntityNameExistenceCheckRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioEntitiesService {
    /**
     * 批量检测资产名称是否存在（模糊匹配，不分页）
     * @returns ApiResponse_EntityNameExistenceCheckResponse_ Successful Response
     * @throws ApiError
     */
    public static checkEntityNamesExistenceApiV1StudioEntitiesExistenceCheckPost({
        requestBody,
        authorization,
    }: {
        requestBody: EntityNameExistenceCheckRequest,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_EntityNameExistenceCheckResponse_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/entities/existence-check',
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
     * 统一实体列表（分页）
     * @returns ApiResponse_PaginatedData_dict_str__Any___ Successful Response
     * @throws ApiError
     */
    public static listEntitiesApiV1StudioEntitiesEntityTypeGet({
        entityType,
        q,
        style,
        visualStyle,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
        projectId,
        authorization,
    }: {
        entityType: string,
        /**
         * 关键字，过滤 name/description
         */
        q?: (string | null),
        /**
         * 题材/风格（单值）
         */
        style?: (string | null),
        /**
         * 画面表现形式（单值：真人/动漫）
         */
        visualStyle?: (string | null),
        order?: (string | null),
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
        /**
         * 按项目过滤（仅对 character 类型有效）
         */
        projectId?: (string | null),
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_dict_str__Any___> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/entities/{entity_type}',
            path: {
                'entity_type': entityType,
            },
            headers: {
                'authorization': authorization,
            },
            query: {
                'q': q,
                'style': style,
                'visual_style': visualStyle,
                'order': order,
                'is_desc': isDesc,
                'page': page,
                'page_size': pageSize,
                'project_id': projectId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一创建实体
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static createEntityApiV1StudioEntitiesEntityTypePost({
        entityType,
        requestBody,
        authorization,
    }: {
        entityType: string,
        requestBody: Record<string, any>,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/entities/{entity_type}',
            path: {
                'entity_type': entityType,
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
     * 统一获取实体
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static getEntityApiV1StudioEntitiesEntityTypeEntityIdGet({
        entityType,
        entityId,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
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
     * 统一更新实体
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static updateEntityApiV1StudioEntitiesEntityTypeEntityIdPatch({
        entityType,
        entityId,
        requestBody,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        requestBody: Record<string, any>,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
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
     * 统一删除实体
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteEntityApiV1StudioEntitiesEntityTypeEntityIdDelete({
        entityType,
        entityId,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
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
     * 统一实体图片列表（分页）
     * @returns ApiResponse_PaginatedData_dict_str__Any___ Successful Response
     * @throws ApiError
     */
    public static listEntityImagesApiV1StudioEntitiesEntityTypeEntityIdImagesGet({
        entityType,
        entityId,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        order?: (string | null),
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_dict_str__Any___> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
            },
            headers: {
                'authorization': authorization,
            },
            query: {
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
     * 统一创建实体图片
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static createEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesPost({
        entityType,
        entityId,
        requestBody,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        requestBody: Record<string, any>,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
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
     * 统一更新实体图片
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static updateEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdPatch({
        entityType,
        entityId,
        imageId,
        requestBody,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        imageId: number,
        requestBody: Record<string, any>,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images/{image_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
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
     * 统一删除实体图片
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdDelete({
        entityType,
        entityId,
        imageId,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        imageId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images/{image_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
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
    /**
     * 列出实体图片候选
     * @returns ApiResponse_list_AssetImageCandidateRead__ Successful Response
     * @throws ApiError
     */
    public static listEntityImageCandidatesApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdCandidatesGet({
        entityType,
        entityId,
        imageId,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        imageId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_list_AssetImageCandidateRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images/{image_id}/candidates',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
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
    /**
     * 添加实体图片候选
     * @returns ApiResponse_list_AssetImageCandidateRead__ Successful Response
     * @throws ApiError
     */
    public static attachEntityImageCandidatesApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdCandidatesPost({
        entityType,
        entityId,
        imageId,
        requestBody,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        imageId: number,
        requestBody: AssetImageCandidateAttachRequest,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_list_AssetImageCandidateRead__> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images/{image_id}/candidates',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
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
     * 采用实体图片候选为当前图
     * @returns ApiResponse_AssetImageCandidateRead_ Successful Response
     * @throws ApiError
     */
    public static adoptEntityImageCandidateApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdCandidatesCandidateIdAdoptPost({
        entityType,
        entityId,
        imageId,
        candidateId,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        imageId: number,
        candidateId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_AssetImageCandidateRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images/{image_id}/candidates/{candidate_id}/adopt',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
                'image_id': imageId,
                'candidate_id': candidateId,
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
     * 删除实体图片候选关系
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteEntityImageCandidateApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdCandidatesCandidateIdDelete({
        entityType,
        entityId,
        imageId,
        candidateId,
        authorization,
    }: {
        entityType: string,
        entityId: string,
        imageId: number,
        candidateId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images/{image_id}/candidates/{candidate_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
                'image_id': imageId,
                'candidate_id': candidateId,
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
