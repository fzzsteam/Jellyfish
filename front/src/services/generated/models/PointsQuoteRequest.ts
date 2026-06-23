/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ModelCategoryKey } from './ModelCategoryKey';
/**
 * 积分试算请求体。
 *
 * - `business_type`: 业务类型标签（如 image_generation / video_generation），仅用于流水归因
 * 与 quote_token 绑定，不参与计价。
 * - `category`: 模型类别，决定计价规则（文本/图片按单价；视频按时长×分辨率×单价）。
 * - `model_id`: 显式模型 ID；为空时按当前用户默认模型解析。
 * - `duration_seconds` / `resolution`: 视频类别的计价参数；文本/图片忽略。
 * - `resolution_profile`: 图片分辨率档位（standard=1K / high=2K），图片类别计价系数来源；
 * 文本/视频忽略，为空按 standard。
 * - `generation_count`: 当前固定为 1（多轮生成能力后续任务再放开）。
 */
export type PointsQuoteRequest = {
    /**
     * 业务类型标签，用于流水归因
     */
    business_type: string;
    /**
     * 模型类别：text/image/video
     */
    category: ModelCategoryKey;
    /**
     * 显式模型 ID；空则用用户默认模型
     */
    model_id?: (string | null);
    /**
     * 视频时长（秒），仅 video 必填
     */
    duration_seconds?: (number | null);
    /**
     * 视频分辨率，仅 video 必填
     */
    resolution?: ('720p' | '1080p' | null);
    /**
     * 图片分辨率档位（standard=1K/high=2K），仅 image 用于计价；空按 standard
     */
    resolution_profile?: ('standard' | 'high' | null);
    /**
     * 生成次数，当前仅支持 1
     */
    generation_count?: number;
};

