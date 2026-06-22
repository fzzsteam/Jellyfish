/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 一致性检查请求（角色混淆）。
 */
export type ScriptConsistencyCheckRequest = {
    /**
     * 项目 ID（异步任务关联可选）
     */
    project_id?: (string | null);
    /**
     * 章节 ID（异步任务关联可选）
     */
    chapter_id?: (string | null);
    /**
     * 完整剧本文本
     */
    script_text: string;
    /**
     * 积分试算凭证（异步与同步接口均必填，Task 5b/6 冻结积分；extract 命中缓存时可不传）
     */
    quote_token?: (string | null);
};

