/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 登录成功返回的令牌对。
 */
export type TokenPairRead = {
    /**
     * 短期访问令牌
     */
    access_token: string;
    /**
     * 长期刷新令牌
     */
    refresh_token: string;
    /**
     * 令牌类型
     */
    token_type?: string;
};

