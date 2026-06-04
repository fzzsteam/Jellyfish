/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 图片候选读模型。
 */
export type AssetImageCandidateRead = {
    id: number;
    target_type: string;
    target_id: number;
    file_id: string;
    source_type: string;
    source_ref?: (string | null);
    is_adopted?: boolean;
};

