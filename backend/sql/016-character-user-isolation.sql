-- 016-character-user-isolation.sql
-- 将 Character 从"项目级资产"升级为"用户级资产"（幂等）。
--
-- 变更概要：
--   1. characters 表新增 user_id（从 project_id→projects.user_id 回填）
--   2. 创建 project_character_links 关联表（仿照 project_actor_links）
--   3. 将现有 characters.project_id 关系迁移为 project_character_links 行
--   4. characters 唯一约束从 (project_id, name) 改为 (user_id, name)
--   5. 删除 characters.project_id 外键与列
--
-- 前置：users 表存在，009 已执行（projects.user_id 已回填）。

-- ============================================================================
-- Step 1: characters 加 user_id
-- ============================================================================
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'characters' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE characters ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 从 projects.user_id 回填（通过现有 project_id 外键）
SET @has_project_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'characters' AND COLUMN_NAME = 'project_id');
SET @sql = IF(@has_project_col > 0,
  "UPDATE characters c
    JOIN projects p ON c.project_id = p.id
    SET c.user_id = p.user_id
    WHERE c.user_id IS NULL",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'characters' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE characters MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'characters' AND CONSTRAINT_NAME = 'fk_characters_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE characters ADD CONSTRAINT fk_characters_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_characters_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============================================================================
-- Step 2: 创建 project_character_links 表
-- ============================================================================
SET @has_tbl = (SELECT COUNT(*) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'project_character_links');
SET @sql = IF(@has_tbl = 0,
  "CREATE TABLE project_character_links (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '关联行 ID',
    project_id VARCHAR(64) NOT NULL COMMENT '项目 ID',
    chapter_id VARCHAR(64) NULL COMMENT '章节 ID',
    shot_id VARCHAR(64) NULL COMMENT '镜头 ID',
    character_id VARCHAR(64) NOT NULL COMMENT '角色 ID',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_pcl_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_pcl_chapter FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE SET NULL,
    CONSTRAINT fk_pcl_shot    FOREIGN KEY (shot_id)    REFERENCES shots(id)    ON DELETE SET NULL,
    CONSTRAINT fk_pcl_character FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
    CONSTRAINT uq_project_character_links_scope UNIQUE (character_id, project_id, chapter_id, shot_id),
    INDEX ix_pcl_project_id   (project_id),
    INDEX ix_pcl_chapter_id   (chapter_id),
    INDEX ix_pcl_shot_id      (shot_id),
    INDEX ix_pcl_character_id (character_id)
  ) COMMENT '项目/章节/镜头 -> 角色关联'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============================================================================
-- Step 3: 将现有 characters.project_id 迁移为 project_character_links 行（项目级）
-- ============================================================================
-- 仅插入尚未存在的行（避免重复执行报唯一约束冲突）
SET @has_project_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'characters' AND COLUMN_NAME = 'project_id');
SET @sql = IF(@has_project_col > 0,
  "INSERT IGNORE INTO project_character_links (project_id, chapter_id, shot_id, character_id)
    SELECT c.project_id, NULL, NULL, c.id
    FROM characters c
    WHERE c.project_id IS NOT NULL",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============================================================================
-- Step 4: 更新 characters 唯一约束：(project_id, name) → (user_id, name)
-- ============================================================================
SET @has_old = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'characters' AND CONSTRAINT_NAME = 'uq_characters_project_name');
SET @sql = IF(@has_old > 0,
  "ALTER TABLE characters DROP INDEX uq_characters_project_name",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_new = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'characters' AND CONSTRAINT_NAME = 'uq_characters_user_name');
SET @sql = IF(@has_new = 0,
  "ALTER TABLE characters ADD UNIQUE KEY uq_characters_user_name (user_id, name)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============================================================================
-- Step 5: 删除 characters.project_id（先删 FK，再删列）
-- ============================================================================
-- 动态查出 project_id 外键约束名并删除
SET @fk_name = (
  SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'characters'
    AND COLUMN_NAME = 'project_id'
    AND REFERENCED_TABLE_NAME = 'projects'
  LIMIT 1
);
SET @sql = IF(@fk_name IS NOT NULL,
  CONCAT('ALTER TABLE characters DROP FOREIGN KEY ', @fk_name),
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 删除 project_id 上的普通索引（若存在）
SET @has_idx = (SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'characters' AND INDEX_NAME = 'ix_characters_project_id');
SET @sql = IF(@has_idx > 0,
  "ALTER TABLE characters DROP INDEX ix_characters_project_id",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 删除 project_id 列
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'characters' AND COLUMN_NAME = 'project_id');
SET @sql = IF(@has_col > 0,
  "ALTER TABLE characters DROP COLUMN project_id",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
