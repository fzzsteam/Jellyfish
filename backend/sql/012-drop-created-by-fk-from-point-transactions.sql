-- 将 point_transactions.created_by 从外键列改为普通字符串列。
--
-- 为什么：freeze/unfreeze/consume 流水由系统自动触发，不存在真实用户操作人，
-- 需要用固定字符串 "system" 标记系统行为；同时用户主动触发（充值/取消）仍存真实
-- user_id。外键约束不允许存非用户 ID 字符串，故去掉 FK，改为普通 VARCHAR。
-- 数据内容不变，历史行 created_by 仍为有效 user_id 或 NULL，兼容无缝。
--
-- 幂等：用 information_schema 动态查找 created_by 列上的外键，存在才删，
-- 不依赖固定约束名（通过 010 SQL 建表的环境名为 fk_point_transactions_creator，
-- 通过 SQLAlchemy create_all 建表的环境 MySQL 自动命名为 point_transactions_ibfk_3）。

SET @fk_name = (
  SELECT CONSTRAINT_NAME
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'point_transactions'
    AND COLUMN_NAME = 'created_by'
    AND REFERENCED_TABLE_NAME = 'users'
  LIMIT 1
);

SET @sql = IF(
  @fk_name IS NOT NULL,
  CONCAT('ALTER TABLE point_transactions DROP FOREIGN KEY `', @fk_name, '`'),
  'SELECT ''point_transactions.created_by FK already dropped, skipping'''
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
