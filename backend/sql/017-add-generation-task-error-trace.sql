SET @has_generation_tasks_error_trace = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'generation_tasks'
    AND COLUMN_NAME = 'error_trace'
);

SET @add_generation_tasks_error_trace = IF(
  @has_generation_tasks_error_trace = 0,
  "ALTER TABLE generation_tasks ADD COLUMN error_trace LONGTEXT NOT NULL COMMENT '失败异常链路，仅管理员可通过任务中心查看'",
  "SELECT 1"
);
PREPARE stmt_add_generation_tasks_error_trace FROM @add_generation_tasks_error_trace;
EXECUTE stmt_add_generation_tasks_error_trace;
DEALLOCATE PREPARE stmt_add_generation_tasks_error_trace;
