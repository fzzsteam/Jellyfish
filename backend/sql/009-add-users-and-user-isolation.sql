-- 009-add-users-and-user-isolation.sql
-- 为 11 类业务表添加 user_id 归属并将历史数据归属初始管理员（幂等）。
-- 前置：users 表已由 init_db() 建出，且 seed_initial_admin() 已播种管理员。
--
-- 幂等策略：沿用 sql/005 的 information_schema + PREPARE/EXECUTE 写法——
--   先用 information_schema 探测“列是否存在 / 列是否仍为 NULLABLE / 约束是否存在 / 索引是否存在”，
--   再用 IF(...) 决定执行真正的 DDL 还是空操作（'SELECT 1'），从而可重复执行不报错。
-- 回填策略：
--   - 一般表：历史行 user_id 统一归属初始管理员。
--   - prompt_templates：仅回填非系统模板；系统模板（is_system=1）保持 NULL（全用户共享），
--     该表 user_id 保持 NULLABLE，不加 FK，仅加索引。
--   - model_settings：原单行（id=1）回填为管理员，并加 user_id 唯一键 + FK。
--   - actors/scenes/props/costumes：名称唯一约束由全局 (name) 改为按用户 (user_id, name)。

SET @admin_id = (SELECT id FROM users WHERE is_admin = 1 ORDER BY created_at LIMIT 1);

-- ============================================================================
-- 一般表（add col -> backfill -> NOT NULL -> FK + index）
-- 表清单：projects, actors, scenes, props, costumes, files, providers, models,
--         generation_tasks
-- ============================================================================

-- ---------------- projects ----------------
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'projects' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE projects ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE projects SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'projects' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE projects MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'projects' AND CONSTRAINT_NAME = 'fk_projects_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE projects ADD CONSTRAINT fk_projects_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_projects_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------- actors ----------------
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'actors' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE actors ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE actors SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'actors' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE actors MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'actors' AND CONSTRAINT_NAME = 'fk_actors_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE actors ADD CONSTRAINT fk_actors_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_actors_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- actors：名称唯一约束 (name) -> (user_id, name)
SET @has_old = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'actors' AND CONSTRAINT_NAME = 'uq_actors_name');
SET @sql = IF(@has_old > 0, "ALTER TABLE actors DROP INDEX uq_actors_name", 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
SET @has_new = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'actors' AND CONSTRAINT_NAME = 'uq_actors_user_name');
SET @sql = IF(@has_new = 0, "ALTER TABLE actors ADD UNIQUE KEY uq_actors_user_name (user_id, name)", 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------- scenes ----------------
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scenes' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE scenes ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE scenes SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scenes' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE scenes MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scenes' AND CONSTRAINT_NAME = 'fk_scenes_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE scenes ADD CONSTRAINT fk_scenes_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_scenes_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_old = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scenes' AND CONSTRAINT_NAME = 'uq_scenes_name');
SET @sql = IF(@has_old > 0, "ALTER TABLE scenes DROP INDEX uq_scenes_name", 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
SET @has_new = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scenes' AND CONSTRAINT_NAME = 'uq_scenes_user_name');
SET @sql = IF(@has_new = 0, "ALTER TABLE scenes ADD UNIQUE KEY uq_scenes_user_name (user_id, name)", 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------- props ----------------
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'props' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE props ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE props SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'props' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE props MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'props' AND CONSTRAINT_NAME = 'fk_props_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE props ADD CONSTRAINT fk_props_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_props_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_old = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'props' AND CONSTRAINT_NAME = 'uq_props_name');
SET @sql = IF(@has_old > 0, "ALTER TABLE props DROP INDEX uq_props_name", 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
SET @has_new = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'props' AND CONSTRAINT_NAME = 'uq_props_user_name');
SET @sql = IF(@has_new = 0, "ALTER TABLE props ADD UNIQUE KEY uq_props_user_name (user_id, name)", 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------- costumes ----------------
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'costumes' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE costumes ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE costumes SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'costumes' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE costumes MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'costumes' AND CONSTRAINT_NAME = 'fk_costumes_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE costumes ADD CONSTRAINT fk_costumes_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_costumes_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_old = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'costumes' AND CONSTRAINT_NAME = 'uq_costumes_name');
SET @sql = IF(@has_old > 0, "ALTER TABLE costumes DROP INDEX uq_costumes_name", 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
SET @has_new = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'costumes' AND CONSTRAINT_NAME = 'uq_costumes_user_name');
SET @sql = IF(@has_new = 0, "ALTER TABLE costumes ADD UNIQUE KEY uq_costumes_user_name (user_id, name)", 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------- files（FileItem.__tablename__ = 'files'）----------------
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'files' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE files ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE files SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'files' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE files MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'files' AND CONSTRAINT_NAME = 'fk_files_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE files ADD CONSTRAINT fk_files_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_files_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------- providers ----------------
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'providers' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE providers ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE providers SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'providers' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE providers MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'providers' AND CONSTRAINT_NAME = 'fk_providers_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE providers ADD CONSTRAINT fk_providers_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_providers_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------- models ----------------
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'models' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE models ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE models SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'models' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE models MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'models' AND CONSTRAINT_NAME = 'fk_models_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE models ADD CONSTRAINT fk_models_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_models_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------- generation_tasks ----------------
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'generation_tasks' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE generation_tasks ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE generation_tasks SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'generation_tasks' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE generation_tasks MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'generation_tasks' AND CONSTRAINT_NAME = 'fk_generation_tasks_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE generation_tasks ADD CONSTRAINT fk_generation_tasks_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_generation_tasks_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============================================================================
-- prompt_templates（系统模板共享，user_id 保持 NULLABLE，不加 FK，仅加索引）
-- ============================================================================
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prompt_templates' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE prompt_templates ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID（系统模板为 NULL，全用户共享）'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE prompt_templates SET user_id = @admin_id WHERE user_id IS NULL AND is_system = 0;
-- 不收紧为 NOT NULL；不加 FK（保持系统模板 NULL 语义）。仅加索引便于过滤。
SET @has_idx = (SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prompt_templates' AND INDEX_NAME = 'ix_prompt_templates_user_id');
SET @sql = IF(@has_idx = 0,
  "ALTER TABLE prompt_templates ADD INDEX ix_prompt_templates_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============================================================================
-- model_settings（原单行 id=1 回填为管理员；加 user_id 唯一键 + FK）
-- ============================================================================
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'model_settings' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE model_settings ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID（每用户一行）'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE model_settings SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'model_settings' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE model_settings MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID', ADD UNIQUE KEY uq_model_settings_user (user_id), ADD CONSTRAINT fk_model_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
