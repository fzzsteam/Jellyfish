-- 010-add-points-billing.sql
-- 积分计费：新增模型积分单价、生成任务计费单据列，以及用户积分账户与积分流水表（幂等）。
--
-- 幂等策略：沿用 sql/009 的 information_schema + PREPARE/EXECUTE 写法——
--   先用 information_schema 探测"列是否存在 / 约束是否存在 / 索引是否存在 / 表是否存在"，
--   再用 IF(...) 决定执行真正的 DDL 还是空操作（'SELECT 1'），从而可重复执行不报错。
-- 回填策略：
--   - models.unit_points：先加 NULL 列 → 回填 1 → 收紧 NOT NULL DEFAULT 1。
--   - user_points：建表后为存量用户补 0 余额行（排除已存在的）。

-- ============================================================================
-- models.unit_points：新增积分单价列
-- ============================================================================
SET
    @has_col = (
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE
            TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'models'
            AND COLUMN_NAME = 'unit_points'
    );

SET
    @sql = IF(
        @has_col = 0,
        "ALTER TABLE models ADD COLUMN unit_points BIGINT NULL COMMENT '积分单价（单次调用消耗的积分数量）'",
        'SELECT 1'
    );

PREPARE s FROM @sql;

EXECUTE s;

DEALLOCATE PREPARE s;

UPDATE models SET unit_points = 1 WHERE unit_points IS NULL;

SET
    @is_null = (
        SELECT IS_NULLABLE
        FROM information_schema.COLUMNS
        WHERE
            TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'models'
            AND COLUMN_NAME = 'unit_points'
    );

SET
    @sql = IF(
        @is_null = 'YES',
        "ALTER TABLE models MODIFY COLUMN unit_points BIGINT NOT NULL DEFAULT 1 COMMENT '积分单价（单次调用消耗的积分数量，默认 1）'",
        'SELECT 1'
    );

PREPARE s FROM @sql;

EXECUTE s;

DEALLOCATE PREPARE s;

-- ============================================================================
-- generation_tasks.billing_id：新增计费单据列 + 索引
-- ============================================================================
SET
    @has_col = (
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE
            TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'generation_tasks'
            AND COLUMN_NAME = 'billing_id'
    );

SET
    @sql = IF(
        @has_col = 0,
        "ALTER TABLE generation_tasks ADD COLUMN billing_id VARCHAR(64) NULL COMMENT '积分计费单据 ID（可空表示未计费）'",
        'SELECT 1'
    );

PREPARE s FROM @sql;

EXECUTE s;

DEALLOCATE PREPARE s;

SET
    @has_idx = (
        SELECT COUNT(*)
        FROM information_schema.STATISTICS
        WHERE
            TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'generation_tasks'
            AND INDEX_NAME = 'ix_generation_tasks_billing_id'
    );

SET
    @sql = IF(
        @has_idx = 0,
        "ALTER TABLE generation_tasks ADD INDEX ix_generation_tasks_billing_id (billing_id)",
        'SELECT 1'
    );

PREPARE s FROM @sql;

EXECUTE s;

DEALLOCATE PREPARE s;

-- ============================================================================
-- user_points：用户积分账户表（每用户一行）
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_points (
    user_id VARCHAR(64) NOT NULL COMMENT '用户 ID（主键，一行一用户）',
    balance BIGINT NOT NULL DEFAULT 0 COMMENT '积分余额',
    frozen BIGINT NOT NULL DEFAULT 0 COMMENT '冻结积分',
    created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (user_id),
    CONSTRAINT fk_user_points_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_user_points_balance_nonneg CHECK (balance >= 0),
    CONSTRAINT ck_user_points_frozen_nonneg CHECK (frozen >= 0),
    CONSTRAINT ck_user_points_frozen_le_balance CHECK (frozen <= balance)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- 回填：为存量用户补 0 余额行（排除已存在的）
INSERT INTO
    user_points (
        user_id,
        balance,
        frozen,
        created_at,
        updated_at
    )
SELECT id, 0, 0, NOW(), NOW()
FROM users
WHERE
    id NOT IN(
        SELECT user_id
        FROM user_points
    );

-- ============================================================================
-- point_transactions：积分流水表（不可变 append-only）
-- ============================================================================
CREATE TABLE IF NOT EXISTS point_transactions (
    id VARCHAR(64) NOT NULL COMMENT '流水 ID',
    user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID',
    type VARCHAR(32) NOT NULL COMMENT '流水类型：recharge/freeze/consume/unfreeze',
    amount BIGINT NOT NULL COMMENT '本次变更涉及的积分数量，符号随类型变化：recharge 支持正负（正为充值、负为扣减）；freeze/consume/unfreeze 为正数',
    balance_after BIGINT NOT NULL COMMENT '变更后余额',
    frozen_after BIGINT NOT NULL COMMENT '变更后冻结额',
    source VARCHAR(32) NOT NULL COMMENT '来源：system/manual/task/...',
    billing_id VARCHAR(64) NULL COMMENT '计费单据 ID（可空，非业务流程为 NULL）',
    business_type VARCHAR(64) NULL COMMENT '业务类型：image_generation/video_generation/...',
    business_id VARCHAR(64) NULL COMMENT '业务实体 ID（如生成任务 ID）',
    model_id VARCHAR(64) NULL COMMENT '涉及的模型 ID（删除模型时置空）',
    pricing_snapshot JSON NULL COMMENT '下单时计价快照（JSON）',
    remark TEXT NULL COMMENT '备注',
    created_by VARCHAR(64) NULL COMMENT '操作人（删除用户时置空）',
    created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    CONSTRAINT fk_point_transactions_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_point_transactions_model FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE SET NULL,
    CONSTRAINT fk_point_transactions_creator FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- (user_id, created_at) 复合索引（按时间倒序查用户流水的常见场景，左前缀同时覆盖纯 user_id 查询）
SET
    @has_idx = (
        SELECT COUNT(*)
        FROM information_schema.STATISTICS
        WHERE
            TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'point_transactions'
            AND INDEX_NAME = 'ix_point_transactions_user_id_created_at'
    );

SET
    @sql = IF(
        @has_idx = 0,
        "ALTER TABLE point_transactions ADD INDEX ix_point_transactions_user_id_created_at (user_id, created_at)",
        'SELECT 1'
    );

PREPARE s FROM @sql;

EXECUTE s;

DEALLOCATE PREPARE s;

-- (billing_id, type) 唯一约束：同一计费单据的同类型操作只允许一条
SET
    @has_uq = (
        SELECT COUNT(*)
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE
            TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'point_transactions'
            AND CONSTRAINT_NAME = 'uq_point_transactions_billing_type'
    );

SET
    @sql = IF(
        @has_uq = 0,
        "ALTER TABLE point_transactions ADD UNIQUE KEY uq_point_transactions_billing_type (billing_id, type)",
        'SELECT 1'
    );

PREPARE s FROM @sql;

EXECUTE s;

DEALLOCATE PREPARE s;