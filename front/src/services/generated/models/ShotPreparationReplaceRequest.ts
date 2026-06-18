/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShotPreparationLinkEntityType } from './ShotPreparationLinkEntityType';
/**
 * 准备页替换关联实体请求：解除 old_entity_id 关联，关联 new_entity_id。
 */
export type ShotPreparationReplaceRequest = {
    /**
     * 项目 ID
     */
    project_id: string;
    /**
     * 章节 ID
     */
    chapter_id: string;
    /**
     * 准备页关联的实体类型
     */
    entity_type: ShotPreparationLinkEntityType;
    /**
     * 要替换掉的旧实体 ID
     */
    old_entity_id: string;
    /**
     * 要关联的新实体 ID
     */
    new_entity_id: string;
};

