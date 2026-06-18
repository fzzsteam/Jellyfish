/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 管理员创建用户的请求体。
 */
export type UserCreate = {
    /**
     * 用户名
     */
    username: string;
    /**
     * 初始密码
     */
    password: string;
    /**
     * 是否管理员
     */
    is_admin?: boolean;
};

