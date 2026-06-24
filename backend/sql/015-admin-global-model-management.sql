-- 015-admin-global-model-management.sql
-- Provider/Model 全局化：清理非管理员数据、修复悬空外键、删除 user_id 列。
-- 幂等策略：用 information_schema 探测列是否存在，再决定执行真正的 DDL 或空操作。

-- ============================================================
-- 1. 清理非管理员用户的 model_settings（按外键依赖顺序先删）
-- ============================================================
DELETE FROM model_settings
WHERE user_id NOT IN (SELECT id FROM users WHERE is_admin = 1);

-- ============================================================
-- 2. 清理非管理员用户的 models
-- ============================================================
DELETE FROM models
WHERE user_id NOT IN (SELECT id FROM users WHERE is_admin = 1);

-- ============================================================
-- 3. 清理非管理员用户的 providers
-- ============================================================
DELETE FROM providers
WHERE user_id NOT IN (SELECT id FROM users WHERE is_admin = 1);

-- ============================================================
-- 4. 修复管理员 model_settings 中悬空的外键引用（置 NULL）
-- ============================================================
UPDATE model_settings
SET default_text_model_id = NULL
WHERE default_text_model_id IS NOT NULL
  AND default_text_model_id NOT IN (SELECT id FROM models);

UPDATE model_settings
SET default_image_model_id = NULL
WHERE default_image_model_id IS NOT NULL
  AND default_image_model_id NOT IN (SELECT id FROM models);

UPDATE model_settings
SET default_video_model_id = NULL
WHERE default_video_model_id IS NOT NULL
  AND default_video_model_id NOT IN (SELECT id FROM models);

-- ============================================================
-- 5. 删除 providers.user_id 列（先删 FK 与索引）
-- ============================================================
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'providers' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col > 0,
  "ALTER TABLE providers DROP FOREIGN KEY fk_providers_user, DROP INDEX ix_providers_user_id, DROP COLUMN user_id",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============================================================
-- 6. 删除 models.user_id 列（先删 FK 与索引）
-- ============================================================
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'models' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col > 0,
  "ALTER TABLE models DROP FOREIGN KEY fk_models_user, DROP INDEX ix_models_user_id, DROP COLUMN user_id",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
