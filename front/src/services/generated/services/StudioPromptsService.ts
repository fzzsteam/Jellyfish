/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_list_PromptCategoryOptionRead__ } from '../models/ApiResponse_list_PromptCategoryOptionRead__';
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_PromptTemplateRead__ } from '../models/ApiResponse_PaginatedData_PromptTemplateRead__';
import type { ApiResponse_PromptTemplateRead_ } from '../models/ApiResponse_PromptTemplateRead_';
import type { PromptCategory } from '../models/PromptCategory';
import type { PromptTemplateCreate } from '../models/PromptTemplateCreate';
import type { PromptTemplateUpdate } from '../models/PromptTemplateUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioPromptsService {
    /**
     * 提示词模板列表（分页）
     * @returns ApiResponse_PaginatedData_PromptTemplateRead__ Successful Response
     * @throws ApiError
     */
    public static listPromptTemplatesApiV1StudioPromptsGet({
        category,
        q,
        isDefault,
        isSystem,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
        authorization,
    }: {
        /**
         * 按类别过滤
         */
        category?: (PromptCategory | null),
        /**
         * 关键字，过滤 name
         */
        q?: (string | null),
        /**
         * 过滤是否为默认
         */
        isDefault?: (boolean | null),
        /**
         * 过滤是否为系统预置
         */
        isSystem?: (boolean | null),
        order?: (string | null),
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_PromptTemplateRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/prompts',
            headers: {
                'authorization': authorization,
            },
            query: {
                'category': category,
                'q': q,
                'is_default': isDefault,
                'is_system': isSystem,
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
     * 创建提示词模板
     * @returns ApiResponse_PromptTemplateRead_ Successful Response
     * @throws ApiError
     */
    public static createPromptTemplateApiV1StudioPromptsPost({
        requestBody,
        authorization,
    }: {
        requestBody: PromptTemplateCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PromptTemplateRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/prompts',
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
     * 获取提示词类别枚举（含中文映射）
     * @returns ApiResponse_list_PromptCategoryOptionRead__ Successful Response
     * @throws ApiError
     */
    public static listPromptCategoriesApiV1StudioPromptsCategoriesGet({
        authorization,
    }: {
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_list_PromptCategoryOptionRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/prompts/categories',
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取提示词模板详情
     * @returns ApiResponse_PromptTemplateRead_ Successful Response
     * @throws ApiError
     */
    public static getPromptTemplateApiV1StudioPromptsTemplateIdGet({
        templateId,
        authorization,
    }: {
        templateId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PromptTemplateRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/prompts/{template_id}',
            path: {
                'template_id': templateId,
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
     * 局部更新提示词模板
     * @returns ApiResponse_PromptTemplateRead_ Successful Response
     * @throws ApiError
     */
    public static updatePromptTemplateApiV1StudioPromptsTemplateIdPatch({
        templateId,
        requestBody,
        authorization,
    }: {
        templateId: string,
        requestBody: PromptTemplateUpdate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PromptTemplateRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/prompts/{template_id}',
            path: {
                'template_id': templateId,
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
     * 删除提示词模板
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deletePromptTemplateApiV1StudioPromptsTemplateIdDelete({
        templateId,
        authorization,
    }: {
        templateId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/prompts/{template_id}',
            path: {
                'template_id': templateId,
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
