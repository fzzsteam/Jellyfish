---
name: debug-jellyfish
description: 排查 Jellyfish（AI 短剧工作台，FastAPI+Celery+MySQL+Redis）问题时使用。用户贴报错或描述问题（积分对不上、任务卡住、生成失败、连不上、行为异常等）时，按 4 步流程排查：探测环境 → 症状分流 → 取证 → 定位根因。只读取证，绝不臆测；数据库连接走 backend/.env 的 DATABASE_URL，不假设端口。
---

# debug-jellyfish — Jellyfish 问题排查

给 AI 用的项目排查流程。用户报错/报问题时**先取证再下结论**，套用 systematic-debugging 纪律（取证 → 假设 → 验证），禁止在取证前下结论。

## 🔒 安全红线（排查前必读）

- **数据库只读**：仅 `SELECT` / `SHOW` / `DESC` / `EXPLAIN`；禁止 `INSERT` / `UPDATE` / `DELETE` / `DROP` / `ALTER` / `CREATE` 等任何写或 DDL。
- **只查不改**：不修改 `.env` / 配置 / Celery 任务；Redis 只 `GET` / `KEYS`，不 `SET` / `DEL`。
- **凭证不外泄**：DB 密码只用于连接，不写入回复、提交或 skill 正文。

<!-- BUILD ANCHOR -->