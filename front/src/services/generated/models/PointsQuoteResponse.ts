/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 积分试算响应。
 *
 * - `resolved_model_id/name`: 实际解析到的模型（显式或默认）。
 * - `using_default_model`: 是否走了用户默认模型（model_id 为空时为 True）。
 * - `required_points`: 本次生成需扣减的积分。
 * - `available_points`: 当前可用额度（balance - frozen）。
 * - `sufficient`: 可用额度是否足够。
 * - `quote_token`: 短期试算凭证 JWT，确认扣费时回带以防参数被篡改。
 */
export type PointsQuoteResponse = {
    /**
     * 解析后的模型 ID
     */
    resolved_model_id: string;
    /**
     * 解析后的模型名称
     */
    resolved_model_name: string;
    /**
     * 是否使用了用户默认模型
     */
    using_default_model: boolean;
    /**
     * 本次生成需扣减积分
     */
    required_points: number;
    /**
     * 当前可用积分
     */
    available_points: number;
    /**
     * 可用积分是否足够
     */
    sufficient: boolean;
    /**
     * 短期试算凭证 JWT
     */
    quote_token: string;
};

