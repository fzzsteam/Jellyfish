/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 管理员修改用户的请求体（字段均可选，仅更新传入项）。
 */
export type UserUpdate = {
    /**
     * 重置后的新密码
     */
    password?: (string | null);
    /**
     * 启用/禁用
     */
    is_active?: (boolean | null);
    /**
     * 是否管理员
     */
    is_admin?: (boolean | null);
};

