/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 局部更新提示词模板。is_system 仅管理员可修改。
 */
export type PromptTemplateUpdate = {
    /**
     * 模板名称
     */
    name?: (string | null);
    /**
     * 模板内容
     */
    content?: (string | null);
    /**
     * 预览文案
     */
    preview?: (string | null);
    /**
     * 变量名列表（整体替换）
     */
    variables?: (Array<string> | null);
    /**
     * 是否为默认提示词
     */
    is_default?: (boolean | null);
    /**
     * 是否为系统预置（仅管理员有效）
     */
    is_system?: (boolean | null);
};

