/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_ImageGenerationOptionsRead_ } from '../models/ApiResponse_ImageGenerationOptionsRead_';
import type { ApiResponse_list_ProviderSupportedRead__ } from '../models/ApiResponse_list_ProviderSupportedRead__';
import type { ApiResponse_ModelRead_ } from '../models/ApiResponse_ModelRead_';
import type { ApiResponse_ModelSettingsRead_ } from '../models/ApiResponse_ModelSettingsRead_';
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_ModelRead__ } from '../models/ApiResponse_PaginatedData_ModelRead__';
import type { ApiResponse_PaginatedData_ProviderRead__ } from '../models/ApiResponse_PaginatedData_ProviderRead__';
import type { ApiResponse_ProviderRead_ } from '../models/ApiResponse_ProviderRead_';
import type { ApiResponse_VideoGenerationOptionsRead_ } from '../models/ApiResponse_VideoGenerationOptionsRead_';
import type { ModelCategoryKey } from '../models/ModelCategoryKey';
import type { ModelCreate } from '../models/ModelCreate';
import type { ModelSettingsUpdate } from '../models/ModelSettingsUpdate';
import type { ModelUpdate } from '../models/ModelUpdate';
import type { ProviderCreate } from '../models/ProviderCreate';
import type { ProviderUpdate } from '../models/ProviderUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class LlmService {
    /**
     * 列出模型供应商（分页）
     * @returns ApiResponse_PaginatedData_ProviderRead__ Successful Response
     * @throws ApiError
     */
    public static listProvidersApiV1LlmProvidersGet({
        q,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
        authorization,
    }: {
        /**
         * 关键字，过滤 name/description
         */
        q?: (string | null),
        /**
         * 排序字段：name, created_at, updated_at
         */
        order?: (string | null),
        /**
         * 是否倒序
         */
        isDesc?: boolean,
        /**
         * 页码
         */
        page?: number,
        /**
         * 每页条数
         */
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_ProviderRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/llm/providers',
            headers: {
                'authorization': authorization,
            },
            query: {
                'q': q,
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
     * 创建模型供应商
     * @returns ApiResponse_ProviderRead_ Successful Response
     * @throws ApiError
     */
    public static createProviderApiV1LlmProvidersPost({
        requestBody,
        authorization,
    }: {
        requestBody: ProviderCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ProviderRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/llm/providers',
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
     * 列出系统支持的供应商能力
     * @returns ApiResponse_list_ProviderSupportedRead__ Successful Response
     * @throws ApiError
     */
    public static listSupportedProvidersApiV1LlmProvidersSupportedGet({
        category,
        authorization,
    }: {
        /**
         * 按模型类别过滤：text/image/video
         */
        category?: (ModelCategoryKey | null),
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_list_ProviderSupportedRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/llm/providers/supported',
            headers: {
                'authorization': authorization,
            },
            query: {
                'category': category,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取当前默认图片模型的关键帧规格选项
     * @returns ApiResponse_ImageGenerationOptionsRead_ Successful Response
     * @throws ApiError
     */
    public static getImageGenerationOptionsApiV1LlmImageGenerationOptionsGet({
        authorization,
    }: {
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ImageGenerationOptionsRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/llm/image-generation-options',
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取当前默认视频模型的动态比例选项
     * @returns ApiResponse_VideoGenerationOptionsRead_ Successful Response
     * @throws ApiError
     */
    public static getVideoGenerationOptionsApiV1LlmVideoGenerationOptionsGet({
        authorization,
    }: {
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_VideoGenerationOptionsRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/llm/video-generation-options',
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取单个模型供应商
     * @returns ApiResponse_ProviderRead_ Successful Response
     * @throws ApiError
     */
    public static getProviderApiV1LlmProvidersProviderIdGet({
        providerId,
        authorization,
    }: {
        providerId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ProviderRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/llm/providers/{provider_id}',
            path: {
                'provider_id': providerId,
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
     * 更新模型供应商
     * @returns ApiResponse_ProviderRead_ Successful Response
     * @throws ApiError
     */
    public static updateProviderApiV1LlmProvidersProviderIdPatch({
        providerId,
        requestBody,
        authorization,
    }: {
        providerId: string,
        requestBody: ProviderUpdate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ProviderRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/llm/providers/{provider_id}',
            path: {
                'provider_id': providerId,
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
     * 删除模型供应商
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteProviderApiV1LlmProvidersProviderIdDelete({
        providerId,
        authorization,
    }: {
        providerId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/llm/providers/{provider_id}',
            path: {
                'provider_id': providerId,
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
     * 列出模型（分页）
     * @returns ApiResponse_PaginatedData_ModelRead__ Successful Response
     * @throws ApiError
     */
    public static listModelsApiV1LlmModelsGet({
        providerId,
        category,
        q,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
        authorization,
    }: {
        /**
         * 按供应商过滤
         */
        providerId?: (string | null),
        /**
         * 按模型类别过滤
         */
        category?: (ModelCategoryKey | null),
        /**
         * 关键字，过滤 name/description
         */
        q?: (string | null),
        /**
         * 排序字段：name, category, created_at, updated_at
         */
        order?: (string | null),
        /**
         * 是否倒序
         */
        isDesc?: boolean,
        /**
         * 页码
         */
        page?: number,
        /**
         * 每页条数
         */
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_ModelRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/llm/models',
            headers: {
                'authorization': authorization,
            },
            query: {
                'provider_id': providerId,
                'category': category,
                'q': q,
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
     * 创建模型
     * @returns ApiResponse_ModelRead_ Successful Response
     * @throws ApiError
     */
    public static createModelApiV1LlmModelsPost({
        requestBody,
        authorization,
    }: {
        requestBody: ModelCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ModelRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/llm/models',
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
     * 获取单个模型
     * @returns ApiResponse_ModelRead_ Successful Response
     * @throws ApiError
     */
    public static getModelApiV1LlmModelsModelIdGet({
        modelId,
        authorization,
    }: {
        modelId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ModelRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/llm/models/{model_id}',
            path: {
                'model_id': modelId,
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
     * 更新模型
     * @returns ApiResponse_ModelRead_ Successful Response
     * @throws ApiError
     */
    public static updateModelApiV1LlmModelsModelIdPatch({
        modelId,
        requestBody,
        authorization,
    }: {
        modelId: string,
        requestBody: ModelUpdate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ModelRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/llm/models/{model_id}',
            path: {
                'model_id': modelId,
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
     * 删除模型
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteModelApiV1LlmModelsModelIdDelete({
        modelId,
        authorization,
    }: {
        modelId: string,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/llm/models/{model_id}',
            path: {
                'model_id': modelId,
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
     * 获取模型全局设置（单例）
     * @returns ApiResponse_ModelSettingsRead_ Successful Response
     * @throws ApiError
     */
    public static getModelSettingsApiV1LlmModelSettingsGet({
        authorization,
    }: {
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ModelSettingsRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/llm/model-settings',
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新模型全局设置（单例）
     * @returns ApiResponse_ModelSettingsRead_ Successful Response
     * @throws ApiError
     */
    public static updateModelSettingsApiV1LlmModelSettingsPut({
        requestBody,
        authorization,
    }: {
        requestBody: ModelSettingsUpdate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ModelSettingsRead_> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/llm/model-settings',
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
