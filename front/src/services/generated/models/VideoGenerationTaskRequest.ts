/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for creating or previewing a shot video generation task.
 */
export type VideoGenerationTaskRequest = {
    /**
     * Shot ID
     */
    shot_id: string;
    /**
     * Reference mode: first | last | key | first_last | first_last_key | text_only
     */
    reference_mode: 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only';
    /**
     * Video prompt; required for text_only after derivation
     */
    prompt?: (string | null);
    /**
     * Reference image file_id list; count must match reference_mode
     */
    images?: Array<string>;
    /**
     * Video aspect ratio, e.g. 16:9 / 9:16
     */
    ratio: '16:9' | '4:3' | '1:1' | '3:4' | '9:16' | '21:9';
    /**
     * Optional built-in generation model id, e.g. builtin:vidu:video:viduq3
     */
    model_id?: (string | null);
};

