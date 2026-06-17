/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShotPreparationLinkEntityType } from './ShotPreparationLinkEntityType';
export type ShotPreparationUnlinkRequest = {
    /**
     * 准备页关联的实体类型
     */
    entity_type: ShotPreparationLinkEntityType;
    /**
     * 要解除关联的实体 ID
     */
    entity_id: string;
    /**
     * 候选项 ID，用于精确定位要忽略的候选；多个候选指向同一实体时可避免操作错误目标
     */
    candidate_id?: number | null;
};
