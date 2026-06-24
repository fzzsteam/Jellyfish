-- 011-optimize-point-transactions-indexes.sql
-- 优化 point_transactions 索引：
--   2. 新增 (type, created_at) 联合索引，支持按流水类型组合过滤
--   3. 新增 business_id 索引，支持按业务实体 ID（如生成任务）反查流水
--
-- 幂等：先探测索引是否存在，再决定执行 DDL 还是空操作，可重复执行不报错。

-- ============================================================================
-- 2. 新增 (type, created_at) 联合索引
-- ============================================================================
SET
    @has_idx = (
        SELECT COUNT(*)
        FROM information_schema.STATISTICS
        WHERE
            TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'point_transactions'
            AND INDEX_NAME = 'ix_point_transactions_type_created_at'
    );

SET
    @sql = IF(
        @has_idx = 0,
        "ALTER TABLE point_transactions ADD INDEX ix_point_transactions_type_created_at (type, created_at)",
        'SELECT 1'
    );

PREPARE s FROM @sql;

EXECUTE s;

DEALLOCATE PREPARE s;

-- ============================================================================
-- 3. 新增 business_id 索引
-- ============================================================================
SET
    @has_idx = (
        SELECT COUNT(*)
        FROM information_schema.STATISTICS
        WHERE
            TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'point_transactions'
            AND INDEX_NAME = 'ix_point_transactions_business_id'
    );

SET
    @sql = IF(
        @has_idx = 0,
        "ALTER TABLE point_transactions ADD INDEX ix_point_transactions_business_id (business_id)",
        'SELECT 1'
    );

PREPARE s FROM @sql;

EXECUTE s;

DEALLOCATE PREPARE s;