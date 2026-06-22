"""应用配置，从环境变量加载。"""

import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Jellyfish API"
    debug: bool = False

    # API
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite+aiosqlite:///./jellyfish.db"

    # JWT 认证
    jwt_secret_key: str = "please-change-me-to-a-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # 积分计费
    # 试算凭证（quote token）有效期：覆盖「试算 → 用户确认扣费」的典型交互窗口。
    # 其他积分计费配置（锁定超时、对账阈值等）由后续任务按需追加。
    points_quote_expire_seconds: int = 300

    # 积分账户 Redis 原子锁配置（Task 3）
    # - points_lock_ttl_ms：持锁 TTL，覆盖一次完整的账户变更（冻结/扣减/解冻/充值）。
    # - points_lock_wait_ms：竞争时最长等待时间，超时抛 PointsOperationBusyError，绝不绕过 Redis。
    # - points_lock_retry_max_backoff_ms：指数退避上限，避免在 Redis 抢锁时打满 CPU。
    points_lock_ttl_ms: int = 30_000
    points_lock_wait_ms: int = 3_000
    points_lock_retry_max_backoff_ms: int = 250

    # 积分冻结补偿（Task 7）：兜底处理逃逸的未结算冻结流水。
    # - points_reconcile_min_age_seconds：冻结被视为"过期"的最小年龄（默认 30 分钟），
    #   足以让正常结算（settle_task_billing_*）先跑完，避免与正常流程抢跑。
    # - points_reconcile_batch_size：单批扫描上限，控制单次 Beat tick 的 DB 负载。
    points_reconcile_min_age_seconds: int = 1800
    points_reconcile_batch_size: int = 100

    # 初始管理员账号（仅在 users 表为空时用于播种）
    initial_admin_username: str = "admin"
    initial_admin_password: str | None = None

    # Redis / Celery Broker
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    celery_broker_url: str | None = None

    # CORS：环境变量中建议使用逗号分隔（更贴近 docker-compose 用法）
    # 也兼容 JSON 数组：'["http://a","http://b"]'
    cors_origins: str = "http://localhost:7788,http://127.0.0.1:7788"

    @property
    def cors_origins_list(self) -> list[str]:
        s = (self.cors_origins or "").strip()
        if not s:
            return []
        if s.startswith("["):
            loaded = json.loads(s)
            if isinstance(loaded, list):
                return [str(x).strip() for x in loaded if str(x).strip()]
            return []
        return [x.strip() for x in s.split(",") if x.strip()]

    # S3 / 对象存储（用于素材文件）
    s3_endpoint_url: str | None = None
    s3_region_name: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket_name: str | None = None
    # 可选：统一前缀，方便按环境/项目隔离，如 "jellyfish/dev"
    s3_base_path: str = ""
    # 可选：对外访问基址（CDN 或自定义域名），为空则使用 S3 自带 URL 或预签名 URL
    s3_public_base_url: str | None = None
    # 寻址风格：virtual（阿里云 OSS ）, path（本地 RustFS/MinIO）
    s3_addressing_style: str | None = None

    def model_post_init(self, __context: object) -> None:
        if not self.celery_broker_url or not str(self.celery_broker_url).strip():
            password_part = f":{self.redis_password}@" if self.redis_password else ""
            self.celery_broker_url = f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
