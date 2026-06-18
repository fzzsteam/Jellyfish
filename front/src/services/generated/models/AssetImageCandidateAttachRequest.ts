/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 把文件加入目标图片槽位候选池。
 */
export type AssetImageCandidateAttachRequest = {
    file_ids: Array<string>;
    source_type?: string;
    source_ref?: (string | null);
    auto_adopt_if_empty?: boolean;
};

