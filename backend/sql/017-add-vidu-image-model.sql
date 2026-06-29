-- 017-add-vidu-image-model.sql
-- 接入 Vidu2 图片模型：为模型管理补齐 Vidu provider 与 viduq2 图片模型。
-- 幂等策略：仅在目标 id 不存在时插入，不覆盖管理员已经配置的 API Key、状态或单价。

INSERT INTO providers (
    id,
    name,
    base_url,
    image_base_url,
    video_base_url,
    api_key,
    api_secret,
    description,
    status,
    created_by,
    created_at,
    updated_at
)
SELECT
    'vidu',
    'Vidu',
    'https://api.vidu.cn',
    'https://api.vidu.cn',
    'https://api.vidu.cn',
    '',
    '',
    'Vidu generation provider. Configure API Key in Model Management before use.',
    'testing',
    'system',
    NOW(),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM providers WHERE id = 'vidu'
);

INSERT INTO models (
    id,
    name,
    category,
    provider_id,
    params,
    unit_points,
    description,
    created_by,
    created_at,
    updated_at
)
SELECT
    'vidu-viduq2-image',
    'viduq2',
    'image',
    'vidu',
    JSON_OBJECT(
        'endpoint', '/ent/v2/reference2image',
        'aspect_ratios', JSON_ARRAY('16:9', '4:3', '1:1', '3:4', '9:16'),
        'resolutions', JSON_ARRAY('1080p', '2K')
    ),
    1,
    'Vidu2 text/reference-to-image model. Asset editor sends selected reference images to /ent/v2/reference2image when available.',
    'system',
    NOW(),
    NOW()
WHERE EXISTS (
    SELECT 1 FROM providers WHERE id = 'vidu'
) AND NOT EXISTS (
    SELECT 1 FROM models WHERE id = 'vidu-viduq2-image'
);

UPDATE models
SET
    unit_points = 1,
    params = JSON_SET(
        COALESCE(params, JSON_OBJECT()),
        '$.resolutions',
        JSON_ARRAY('1080p', '2K')
    ),
    description = 'Vidu2 text/reference-to-image model. Asset editor sends selected reference images to /ent/v2/reference2image when available.',
    updated_at = NOW()
WHERE id = 'vidu-viduq2-image'
  AND created_by = 'system';
