/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ModelCategoryKey } from './ModelCategoryKey';
/**
 * System-owned generation model option shown directly in generation panels.
 */
export type BuiltinGenerationModelRead = {
    /**
     * Stable built-in model id passed by generation requests
     */
    id: string;
    /**
     * Provider stable key
     */
    provider: string;
    /**
     * Provider display name
     */
    provider_name: string;
    /**
     * Model category: image/video
     */
    category: ModelCategoryKey;
    /**
     * Provider model name sent to the adapter
     */
    name: string;
    /**
     * UI display name
     */
    display_name: string;
    /**
     * Usage scenario description
     */
    description?: string;
    /**
     * Whether this is the default model for the category
     */
    recommended?: boolean;
};

