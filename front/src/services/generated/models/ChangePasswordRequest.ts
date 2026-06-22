/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 当前用户自助修改密码的请求体。
 */
export type ChangePasswordRequest = {
    /**
     * 当前密码
     */
    current_password: string;
    /**
     * 新密码
     */
    new_password: string;
};

