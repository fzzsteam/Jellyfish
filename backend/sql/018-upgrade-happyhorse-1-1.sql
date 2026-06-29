-- 018-upgrade-happyhorse-1-1.sql
-- 阿里百炼 HappyHorse 官方模型名从 1.0 升级到 1.1。
-- 幂等策略：仅替换模型名中的 happyhorse-1.0- 前缀，不修改模型 ID、供应商、单价或默认模型引用。

UPDATE models
SET
    name = REPLACE(name, 'happyhorse-1.0-', 'happyhorse-1.1-'),
    updated_at = NOW()
WHERE category = 'video'
  AND name LIKE 'happyhorse-1.0-%';
