-- 013-add-point-transactions-cascade-group-id.sql
-- 为 point_transactions 表新增 cascade_group_id 列及索引。
--
-- cascade_group_id 用于将同一次级联收费操作的所有流水（freeze/consume/unfreeze）
-- 关联起来；值取该次操作的 root billing_id。充值与手动调整记录该列为 NULL。
--
-- 幂等：通过 information_schema 探测列是否存在，可重复执行不报错。

SET @dbname = DATABASE();
SET @exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'point_transactions'
      AND COLUMN_NAME = 'cascade_group_id'
);
SET @sql = IF(@exists = 0,
    'ALTER TABLE point_transactions
        ADD COLUMN cascade_group_id VARCHAR(64) NULL COMMENT "级联分组键",
        ADD INDEX ix_point_transactions_cascade_group_id (cascade_group_id)',
    'SELECT "column cascade_group_id already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;