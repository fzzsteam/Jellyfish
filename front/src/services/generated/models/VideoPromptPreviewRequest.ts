/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 视频提示词预览请求体：仅包含提示词构建所需字段，不含计费参数。
 */
export type VideoPromptPreviewRequest = {
    /**
     * 镜头 ID
     */
    shot_id: string;
    /**
     * 参考模式：first | last | key | first_last | first_last_key | text_only
     */
    reference_mode: 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only';
    /**
     * 视频提示词（text_only 必填；非文本模式可作为补充描述）
     */
    prompt?: (string | null);
    /**
     * 参考图 file_id 列表
     */
    images?: Array<string>;
    /**
     * 视频画幅比例，如 16:9 / 4:3 / 1:1 / 3:4 / 9:16
     */
    ratio?: ('16:9' | '4:3' | '1:1' | '3:4' | '9:16' | '21:9' | null);
};

