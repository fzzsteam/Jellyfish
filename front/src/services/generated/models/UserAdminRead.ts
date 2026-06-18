/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 管理员视角的用户信息。
 */
export type UserAdminRead = {
    /**
     * 用户 ID
     */
    id: string;
    /**
     * 用户名
     */
    username: string;
    /**
     * 是否管理员
     */
    is_admin: boolean;
    /**
     * 是否启用
     */
    is_active: boolean;
};

