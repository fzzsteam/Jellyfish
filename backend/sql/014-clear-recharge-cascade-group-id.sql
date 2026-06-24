-- 014-clear-recharge-cascade-group-id.sql
-- 清空已有充值/调整记录的 cascade_group_id，确保存量数据与新的 NULL 语义一致。
--
-- recharge 类型由 ledger.recharge 写入，source='admin'，属于单笔流水，
-- 不参与按 cascade_group_id 的级联操作分组。
--
-- 幂等：重复执行不会改变已清空的记录。

UPDATE point_transactions
SET cascade_group_id = NULL
WHERE type = 'recharge' AND cascade_group_id IS NOT NULL;
