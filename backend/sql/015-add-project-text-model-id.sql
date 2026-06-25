-- Add project-level text model selection for script agents.

SET @db_name = DATABASE();

SET @has_text_model_col = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @db_name
    AND TABLE_NAME = 'projects'
    AND COLUMN_NAME = 'text_model_id'
);

SET @sql = IF(
  @has_text_model_col = 0,
  'ALTER TABLE projects ADD COLUMN text_model_id VARCHAR(64) NULL AFTER default_video_ratio',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has_text_model_idx = (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @db_name
    AND TABLE_NAME = 'projects'
    AND INDEX_NAME = 'ix_projects_text_model_id'
);

SET @sql = IF(
  @has_text_model_idx = 0,
  'CREATE INDEX ix_projects_text_model_id ON projects (text_model_id)',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has_text_model_fk = (
  SELECT COUNT(*)
  FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = @db_name
    AND TABLE_NAME = 'projects'
    AND CONSTRAINT_NAME = 'fk_projects_text_model_id_models'
    AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);

SET @sql = IF(
  @has_text_model_fk = 0,
  'ALTER TABLE projects ADD CONSTRAINT fk_projects_text_model_id_models FOREIGN KEY (text_model_id) REFERENCES models(id) ON DELETE SET NULL',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
