/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 视频生成任务请求体。
 *
 * 显式 `model_id` 用于覆盖默认视频模型，保证工作室里的模型选择能进入实际任务。
 */
export type VideoGenerationTaskRequest = {
    /**
     * 镜头 ID
     */
    shot_id: string;
    /**
     * 可选视频模型 ID（models.id）；不传则使用当前用户的默认视频模型
     */
    model_id?: (string | null);
    /**
     * 参考模式：first | last | key | first_last | first_last_key | text_only
     */
    reference_mode: 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only';
    /**
     * 视频提示词（text_only 必填；非文本模式可作为补充描述）
     */
    prompt?: (string | null);
    /**
     * 参考图 file_id 列表，数量需与 reference_mode 严格匹配
     */
    images?: Array<string>;
    /**
     * 视频画幅比例，如 16:9 / 9:16
     */
    ratio: '16:9' | '4:3' | '1:1' | '3:4' | '9:16' | '21:9';
};

