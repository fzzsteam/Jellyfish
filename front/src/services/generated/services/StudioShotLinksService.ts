/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_Any__ } from '../models/ApiResponse_PaginatedData_Any__';
import type { ApiResponse_ProjectActorLinkRead_ } from '../models/ApiResponse_ProjectActorLinkRead_';
import type { ApiResponse_ProjectCharacterLinkRead_ } from '../models/ApiResponse_ProjectCharacterLinkRead_';
import type { ApiResponse_ProjectCostumeLinkRead_ } from '../models/ApiResponse_ProjectCostumeLinkRead_';
import type { ApiResponse_ProjectPropLinkRead_ } from '../models/ApiResponse_ProjectPropLinkRead_';
import type { ApiResponse_ProjectSceneLinkRead_ } from '../models/ApiResponse_ProjectSceneLinkRead_';
import type { ProjectAssetLinkCreate } from '../models/ProjectAssetLinkCreate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioShotLinksService {
    /**
     * 项目-章节-镜头-实体关联列表（分页）
     * @returns ApiResponse_PaginatedData_Any__ Successful Response
     * @throws ApiError
     */
    public static listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType,
        projectId,
        chapterId,
        shotId,
        assetId,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
        authorization,
    }: {
        entityType: string,
        projectId?: (string | null),
        chapterId?: (string | null),
        shotId?: (string | null),
        assetId?: (string | null),
        order?: (string | null),
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_PaginatedData_Any__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shot-links/{entity_type}',
            path: {
                'entity_type': entityType,
            },
            headers: {
                'authorization': authorization,
            },
            query: {
                'project_id': projectId,
                'chapter_id': chapterId,
                'shot_id': shotId,
                'asset_id': assetId,
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
     * 创建项目-章节-镜头-演员关联
     * @returns ApiResponse_ProjectActorLinkRead_ Successful Response
     * @throws ApiError
     */
    public static createProjectActorLinkApiV1StudioShotLinksActorPost({
        requestBody,
        authorization,
    }: {
        requestBody: ProjectAssetLinkCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ProjectActorLinkRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/shot-links/actor',
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
     * 删除项目-章节-镜头-演员关联
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteProjectActorLinkApiV1StudioShotLinksActorLinkIdDelete({
        linkId,
        authorization,
    }: {
        linkId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/shot-links/actor/{link_id}',
            path: {
                'link_id': linkId,
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
     * 创建项目-章节-镜头-场景关联
     * @returns ApiResponse_ProjectSceneLinkRead_ Successful Response
     * @throws ApiError
     */
    public static createProjectSceneLinkApiV1StudioShotLinksScenePost({
        requestBody,
        authorization,
    }: {
        requestBody: ProjectAssetLinkCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ProjectSceneLinkRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/shot-links/scene',
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
     * 删除项目-章节-镜头-场景关联
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteProjectSceneLinkApiV1StudioShotLinksSceneLinkIdDelete({
        linkId,
        authorization,
    }: {
        linkId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/shot-links/scene/{link_id}',
            path: {
                'link_id': linkId,
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
     * 创建项目-章节-镜头-道具关联
     * @returns ApiResponse_ProjectPropLinkRead_ Successful Response
     * @throws ApiError
     */
    public static createProjectPropLinkApiV1StudioShotLinksPropPost({
        requestBody,
        authorization,
    }: {
        requestBody: ProjectAssetLinkCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ProjectPropLinkRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/shot-links/prop',
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
     * 删除项目-章节-镜头-道具关联
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteProjectPropLinkApiV1StudioShotLinksPropLinkIdDelete({
        linkId,
        authorization,
    }: {
        linkId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/shot-links/prop/{link_id}',
            path: {
                'link_id': linkId,
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
     * 创建项目-章节-镜头-服装关联
     * @returns ApiResponse_ProjectCostumeLinkRead_ Successful Response
     * @throws ApiError
     */
    public static createProjectCostumeLinkApiV1StudioShotLinksCostumePost({
        requestBody,
        authorization,
    }: {
        requestBody: ProjectAssetLinkCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ProjectCostumeLinkRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/shot-links/costume',
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
     * 删除项目-章节-镜头-服装关联
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteProjectCostumeLinkApiV1StudioShotLinksCostumeLinkIdDelete({
        linkId,
        authorization,
    }: {
        linkId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/shot-links/costume/{link_id}',
            path: {
                'link_id': linkId,
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
     * 创建项目-章节-镜头-角色关联
     * @returns ApiResponse_ProjectCharacterLinkRead_ Successful Response
     * @throws ApiError
     */
    public static createProjectCharacterLinkApiV1StudioShotLinksCharacterPost({
        requestBody,
        authorization,
    }: {
        requestBody: ProjectAssetLinkCreate,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_ProjectCharacterLinkRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/shot-links/character',
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
     * 删除项目-章节-镜头-角色关联
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteProjectCharacterLinkApiV1StudioShotLinksCharacterLinkIdDelete({
        linkId,
        authorization,
    }: {
        linkId: number,
        authorization?: (string | null),
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/shot-links/character/{link_id}',
            path: {
                'link_id': linkId,
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
