"""Celery 应用实例。

最小落地原则：
- 仅把 Celery 当作执行层与 broker 客户端；
- 任务状态/结果真相仍然回写 GenerationTask；
- 第一阶段不依赖 Celery result backend。
"""

from celery import Celery
from celery.signals import worker_process_init

from app.config import settings
from app.core.db import reset_db_runtime


celery_app = Celery(
    "jellyfish",
    broker=settings.celery_broker_url,
    include=["app.tasks.execute_task", "app.tasks.points", "app.tasks.task_reconciliation"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    timezone="Asia/Shanghai",
    enable_utc=False,
    # 全局超时兜底：所有已注册 executor 里最长的显式超时是 video_generation 的 3600s
    # （见 task_registry.py），这里留出余量设到 3900/4200s，正常任务不会触碰到。
    # 背景：script_divide 曾经在积分冻结阶段卡进一次没有 socket 超时的 Redis 调用，
    # 应用层的 DivideTaskExecutor.timeout_seconds 只在阶段之间做协作式检查、不会打断
    # 正在阻塞的单次调用，导致一个任务实打实挂了 11+ 小时，只能人工在 UI 里取消。
    # task_soft_time_limit 到点后在 worker 内抛 SoftTimeLimitExceeded（可被现有的
    # except Exception 捕获，走正常的失败结算+解冻流程）；task_time_limit 是最后一道
    # 硬限制，SoftTimeLimitExceeded 未能让任务及时退出时由 Celery 直接 SIGKILL 子进程，
    # 保证 worker 槽位最终一定能被释放。
    task_soft_time_limit=3900,
    task_time_limit=4200,
    # 全局并发上限：所有任务类型/供应商共享同一个 worker 进程池，超出的任务留在
    # 队列里排队（Celery 拉取式消费的默认行为），不需要额外的限流/排队代码。
    # 等价于 CLI 的 --concurrency，写在这里而不是部署命令行里，方便只改环境变量
    # （CELERY_WORKER_CONCURRENCY）调整、不用碰 docker-compose.yml/supervisord.conf。
    worker_concurrency=settings.celery_worker_concurrency,
)

# Celery Beat 定时调度表。
# 注意：生产环境必须只启动一个 Beat 进程（见 deploy/docker/supervisord.conf 与
# deploy/compose/docker-compose.yml 中 celery-beat 服务的注释），否则同一任务会被重复触发。
celery_app.conf.beat_schedule = {
    "reconcile-stale-point-freezes": {
        "task": "points.reconcile_stale_freezes",
        "schedule": 300.0,
    },
    # 必须先于/与 reconcile-stale-point-freezes 配合运行：GenerationTask 被硬杀死后
    # 永远停在 running，freeze 对账会因为"任务仍在跑"而永远跳过，见
    # app/services/worker/task_reconciliation.py 的设计说明。
    "reconcile-stale-generation-tasks": {
        "task": "tasks.reconcile_stale_generation_tasks",
        "schedule": 300.0,
    },
}


@worker_process_init.connect
def _reset_async_db_runtime(**_: object) -> None:
    """Celery prefork 子进程启动后，重建 async DB 运行时。"""

    reset_db_runtime()
