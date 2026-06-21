/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UserAdminRead } from './UserAdminRead';
/**
 * 管理员重置密码后返回的一次性结果：用户信息 + 临时密码。
 */
export type ResetPasswordRead = {
    user: UserAdminRead;
    /**
     * 一次性临时密码，仅本次返回
     */
    temporary_password: string;
};

