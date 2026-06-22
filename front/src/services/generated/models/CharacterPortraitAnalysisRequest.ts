/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 人物画像缺失信息分析请求。
 */
export type CharacterPortraitAnalysisRequest = {
    /**
     * 任务关联实体 ID（资产页恢复任务可选）
     */
    relation_entity_id?: (string | null);
    /**
     * 项目 ID（异步任务关联可选）
     */
    project_id?: (string | null);
    /**
     * 章节 ID（异步任务关联可选）
     */
    chapter_id?: (string | null);
    /**
     * 原文人物上下文（可为空；用于提供额外背景，帮助判断缺失信息）
     */
    character_context?: (string | null);
    /**
     * 原文人物描述
     */
    character_description: string;
    /**
     * 积分试算凭证（异步与同步接口均必填，Task 5b/6 冻结积分；extract 命中缓存时可不传）
     */
    quote_token?: (string | null);
};

