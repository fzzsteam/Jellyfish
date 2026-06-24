"""积分试算与领域错误编排服务。

为什么存在：
    把「模型解析 → 计价 → 余额查询 → 试算凭证签发」这条链路收敛到一处，并对上层 API
    暴露统一的领域错误 `PointsDomainError`（携带稳定字符串 code、HTTP 状态码、结构化 data），
    避免 HTTPException 散落各处导致前端无法按稳定 code 分支。

职责边界：
    - 不直接读写积分账户状态（冻结/扣减/解冻/充值由 `ledger.py` 负责）。
    - 只做读侧的试算与查询；写侧的扣费/确认在后续任务复用 ledger。
    - Task 5a 起新增 `freeze_for_task` / `settle_task_billing_sync`：把异步任务与积分账本
      桥接起来——下单时按 quote_token 冻结，任务终态时由 Celery worker 统一结算。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from collections import OrderedDict

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_maker
from app.models.llm import Model, ModelCategoryKey
from app.models.points import PointTransaction, PointTransactionType
from app.schemas.points import PointsQuoteResponse, PointsSummaryRead
from app.services.llm.resolver import get_default_model_by_category
from app.services.points import (
    UnsupportedResolutionError,
    calculate_points,
    create_quote_token,
    decode_quote_token,
    freeze_points,
    get_points,
    hash_quote_params,
)
from app.services.points.locks import PointsOperationBusyError
from app.services.points.quote_tokens import QuoteClaims, QuoteTokenError

logger = logging.getLogger(__name__)


class PointsDomainError(Exception):
    """积分领域错误：携带稳定字符串 code、HTTP 状态码与结构化 data。

    为什么不复用 HTTPException：
        HTTPException 的 detail 通常是裸字符串，无法承载结构化字段（available/required/shortfall、
        新试算结果等），且会被 main.py 的通用 HTTPException 处理器吞掉结构。本类独立于
        HTTPException，由 main.py 注册专属处理器序列化为 ApiResponse 信封，稳定 code 放在
        `data.error_code`，便于前端按 code 精确分支。
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code  # 稳定字符串：INSUFFICIENT_POINTS / POINTS_QUOTE_CHANGED / POINTS_OPERATION_BUSY / MODEL_NOT_OWNED
        self.message = message
        self.status_code = status_code
        self.data = data or {}


def build_insufficient_error(*, available: int, required: int, shortfall: int) -> PointsDomainError:
    """构造余额不足错误（HTTP 402），data 携带 available/required/shortfall。"""
    return PointsDomainError(
        code="INSUFFICIENT_POINTS",
        message="insufficient points",
        status_code=402,
        data={"available": available, "required": required, "shortfall": shortfall},
    )


def build_quote_changed_error(*, new_quote: dict[str, Any]) -> PointsDomainError:
    """构造试算已变更错误（HTTP 409），data 携带最新试算结果。

    为什么需要：用户持旧 quote_token 确认扣费时，若服务端按当前单价/参数重算的结果与 token 中
    required_points 不一致，必须拒绝并回带最新试算，让前端重新确认。Task 5/6 的扣费确认会触发。
    """
    return PointsDomainError(
        code="POINTS_QUOTE_CHANGED",
        message="points quote has changed, please re-quote",
        status_code=409,
        data=dict(new_quote),
    )


def build_busy_error(*, user_id: str) -> PointsDomainError:
    """构造账户操作繁忙错误（HTTP 503），提示稍后重试。"""
    return PointsDomainError(
        code="POINTS_OPERATION_BUSY",
        message="points operation busy, please retry later",
        status_code=503,
        data={"user_id": user_id},
    )


def build_model_not_owned_error(*, model_id: str, user_id: str) -> PointsDomainError:
    """构造模型归属校验失败错误（HTTP 403），拒绝借用他人模型计价。

    为什么需要：`resolver.get_model_by_category` 不会校验显式 model_id 是否归属当前用户
    （模型按用户严格隔离），试算必须显式补这道校验，否则用户可借用他人模型的单价试算。
    """
    return PointsDomainError(
        code="MODEL_NOT_OWNED",
        message=f"model {model_id} does not belong to user {user_id}",
        status_code=403,
        data={"model_id": model_id, "user_id": user_id},
    )


# ---------------------------------------------------------------------------
# Task 5a：异步任务积分冻结与结算基础设施
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FrozenBilling:
    """`freeze_for_task` 返回的冻结句柄。

    - `billing_id`：本次冻结的单据 ID，作为 freeze ↔ task 行之间的稳定关联键
      （5b/5c 会把它写到 `GenerationTask.billing_id`，worker 终态结算据此回溯）。
    - `required_points`：本次冻结的积分数量（= 重算后的 required_points）。
    - `model_id`：实际参与计价的模型 ID（来自 quote_token，权威）。
    - `business_type`：业务类型（如 `video_generation`），透传到账本流水。
    - `snapshot`：计价快照，落库到 freeze 流水的 `pricing_snapshot`，便于对账。
    """

    billing_id: str
    required_points: int
    model_id: str
    business_type: str
    snapshot: dict[str, Any]


async def freeze_for_task(
    db: AsyncSession,
    *,
    user_id: str,
    quote_token: str,
    business_type: str,
    category: ModelCategoryKey,
    model_id: str | None,
    cascade_group_id: str | None = None,
    duration_seconds: int | None = None,
    resolution: str | None = None,
    resolution_profile: str | None = None,
) -> FrozenBilling:
    """按 quote_token 冻结积分（异步任务下单入口）。

    流程（与 `quote_points` 对称，区别在于这里是「写侧」冻结）：
    1. 解析并校验 quote_token（绑定 user_id）——失败抛 `POINTS_QUOTE_INVALID`(400)。
    2. 以 token 中的 `model_id` 为权威，重新取 Model 行并做归属 + 类别校验
       （`resolver` 不校验归属，这里显式补；不归属抛 `MODEL_NOT_OWNED`(403)）。
       `model_id` 入参与 `claims.model_id` 必须一致（若显式传入），否则视为请求与报价单据不
       一致 → `POINTS_QUOTE_CHANGED`(409)（客户端试图对报价单据之外的模型计费）。
    3. 用当前模型单价 + 入参重新计价，得到 `required_points`。
    4. 一致性校验：
       - 若重算 `required_points != claims.required_points` → `POINTS_QUOTE_CHANGED`(409)
         （单价自试算后调整，必须重新确认）。
       - 重算 `params_hash`（duration/resolution）若与 token 中不符 → `POINTS_QUOTE_CHANGED`
         （入参被篡改）。
    5. 生成 `billing_id`，构造 `snapshot`，调用 `freeze_points` 落账本：
       - 余额不足 → `INSUFFICIENT_POINTS`(402)。
       - 账户操作繁忙 → `POINTS_OPERATION_BUSY`(503)。
    6. 返回 `FrozenBilling` 句柄，供 5b/5c 写入任务行。

    注意：`business_id=None`，因为冻结发生在任务行创建之前；`billing_id` 才是稳定关联键。

    IMPORTANT: 冻结的回滚契约。`freeze_points` 内部会自行 COMMIT（见 ledger.py），因此
    本函数返回时积分冻结已落库且不可回滚事务。调用方在 freeze 成功后若任务创建/入库失败,
    必须调用 `unfreeze_frozen(db, user_id=..., billing_id=frozen.billing_id)` 回滚,否则冻结
    将悬挂直至 Celery Beat 补偿(Task 7)。本函数自身不做任务行写入,无法代为回滚。
    """
    # 1. 解析 quote_token
    try:
        claims = decode_quote_token(quote_token, expected_user_id=user_id)
    except QuoteTokenError:
        raise PointsDomainError(
            code="POINTS_QUOTE_INVALID",
            message="quote token is invalid, expired, or bound to another user",
            status_code=400,
            data={},
        ) from None

    # 2. 以 token 中 model_id 为权威取模型 + 归属 + 类别校验。
    # 若调用方显式传入 model_id 且与 token 绑定的 model_id 不一致,视为请求与报价单据不一致
    # (客户端试图对报价之外的模型计费) → POINTS_QUOTE_CHANGED(409)。
    if model_id is not None and model_id != claims.model_id:
        raise PointsDomainError(
            code="POINTS_QUOTE_CHANGED",
            message=(
                f"request model_id={model_id} != quoted model_id={claims.model_id}; "
                "client attempted to bill a different model than the one quoted"
            ),
            status_code=409,
            data={"requested_model_id": model_id, "quoted_model_id": claims.model_id},
        )
    model = await db.get(Model, claims.model_id)
    if model is None:
        raise PointsDomainError(
            code="POINTS_QUOTE_INVALID",
            message=f"model {claims.model_id} bound in quote token not found",
            status_code=400,
            data={"model_id": claims.model_id},
        )
    if model.user_id != user_id:
        raise build_model_not_owned_error(model_id=model.id, user_id=user_id)
    if model.category != category:
        raise PointsDomainError(
            code="MODEL_CATEGORY_MISMATCH",
            message=f"model {model.id} category={model.category} != requested={category}",
            status_code=400,
            data={"model_id": model.id, "model_category": str(model.category), "requested_category": str(category)},
        )

    # 3. 重新计价
    required_points = calculate_points(
        category=category,
        unit_points=model.unit_points,
        duration_seconds=duration_seconds,
        resolution=resolution,
        resolution_profile=resolution_profile,
        generation_count=1,
    )

    # 4. 一致性校验：价格变更 / 参数篡改
    if required_points != claims.required_points:
        raise build_quote_changed_error(
            new_quote={
                "category": str(category),
                "model_id": model.id,
                "unit_points": model.unit_points,
                "duration_seconds": duration_seconds,
                "resolution": resolution,
                "required_points": required_points,
                "claimed_required_points": claims.required_points,
            }
        )

    recomputed_params_hash = hash_quote_params(
        {
            "category": str(category),
            "duration_seconds": duration_seconds,
            "resolution": resolution,
            "resolution_profile": resolution_profile,
            "generation_count": 1,
        }
    )
    if recomputed_params_hash != claims.params_hash:
        raise build_quote_changed_error(
            new_quote={
                "category": str(category),
                "model_id": model.id,
                "unit_points": model.unit_points,
                "duration_seconds": duration_seconds,
                "resolution": resolution,
                "required_points": required_points,
                "reason": "params_hash mismatch",
            }
        )

    # 5. 冻结
    billing_id = uuid.uuid4().hex
    snapshot = {
        "category": str(category),
        "unit_points": model.unit_points,
        "duration_seconds": duration_seconds,
        "resolution": resolution,
        "resolution_profile": resolution_profile,
        "required_points": required_points,
    }
    from app.services.points.ledger import InsufficientPointsError

    try:
        await freeze_points(
            db,
            user_id=user_id,
            billing_id=billing_id,
            amount=required_points,
            model_id=model.id,
            business_type=business_type,
            business_id=None,
            cascade_group_id=cascade_group_id,
            snapshot=snapshot,
            created_by=user_id,
        )
    except InsufficientPointsError as e:
        raise build_insufficient_error(
            available=e.available, required=e.required, shortfall=e.shortfall
        ) from e
    except PointsOperationBusyError as e:
        _ = e  # 仅用于类型收敛
        raise build_busy_error(user_id=user_id) from e

    return FrozenBilling(
        billing_id=billing_id,
        required_points=required_points,
        model_id=model.id,
        business_type=business_type,
        snapshot=snapshot,
    )


async def freeze_for_call(
    db: AsyncSession,
    *,
    user_id: str,
    quote_token: str,
    business_type: str,
) -> FrozenBilling:
    """同步文本类调用的积分冻结入口（Task 6）。

    为什么存在：
        同步文本端点（divide / merge / variant / consistency / character / prop / scene /
        costume / optimize / simplify / extract）在请求线程内直接调用 LLM agent，不走 Celery
        任务编排，因此不能复用 `freeze_for_task` 的 task 行通道。本函数是「文本专用薄包装」：
        固定 `category=ModelCategoryKey.text`、`model_id=None`、`duration_seconds=None`、
        `resolution=None` 调用 `freeze_for_task`，其余校验（quote 解析、归属、价格一致性、余额）
        全部复用 freeze_for_task 的既有逻辑，避免双份维护。

    Args:
        db: 异步会话。
        user_id: 当前用户 ID。
        quote_token: 试算凭证（必须绑定当前 user 与一个 text 类模型）。
        business_type: 业务类型（如 `script_divide`），透传到账本流水。

    Returns:
        FrozenBilling 句柄（供 `run_billed_text_operation` 在成功时 consume / 失败时 unfreeze）。
    """
    return await freeze_for_task(
        db,
        user_id=user_id,
        quote_token=quote_token,
        business_type=business_type,
        category=ModelCategoryKey.text,
        model_id=None,
        duration_seconds=None,
        resolution=None,
    )


# 泛型类型变量：run_billed_text_operation 的 operation 返回值类型。
T = TypeVar("T")


async def run_billed_text_operation(
    db: AsyncSession,
    *,
    user_id: str,
    quote_token: str,
    business_type: str,
    operation: Callable[[], Awaitable[T]],
) -> T:
    """同步文本操作的统一计费执行器（Task 6）。

    统一编排「冻结 → 执行业务 → 成功消费 / 失败解冻」三个阶段，保证：
    - 成功：冻结积分被 consume（余额与冻结额同步减少）。
    - 业务异常（LLM 失败或后处理失败）：冻结积分被 unfreeze（余额不变、冻结额释放）。
    - 冻结阶段失败（余额不足 / 报价变更 / 账户繁忙）：直接上抛 PointsDomainError，operation
      不会被执行（调用方据此判定 LLM 未被调用）。

    为什么 operation 是 async：
        各端点的 agent 调用是同步阻塞（LangChain `.invoke`），调用方应在 operation 内部用
        `asyncio.to_thread` 包装同步 agent 调用，并把所有后置异步业务逻辑（如 write_to_db、
        缓存写入）一并放入同一 operation，确保任意阶段失败都走 unfreeze 分支。

    Args:
        db: 异步会话（与路由层 Depends(get_db) 同一会话，operation 内的写库操作复用它）。
        user_id: 当前用户 ID。
        quote_token: 试算凭证（同步端点强制要求）。
        business_type: 稳定业务类型字符串（如 `script_divide`）。
        operation: 无参 async 可调用，封装真实的 LLM 调用 + 后处理。

    Returns:
        operation 的返回值。

    Raises:
        PointsDomainError: 冻结阶段（INSUFFICIENT_POINTS / POINTS_QUOTE_CHANGED /
            POINTS_OPERATION_BUSY 等）—— 调用方应让其上抛交由 main.py 处理器序列化。
    """
    frozen = await freeze_for_call(
        db,
        user_id=user_id,
        quote_token=quote_token,
        business_type=business_type,
    )
    # 局部导入 consume/unfreeze 避免与 ledger 形成循环依赖（与 settle_task_billing_async 同款）。
    from app.services.points import consume_frozen, unfreeze_frozen

    try:
        result = await operation()
    except BaseException:
        # 任何异常（含 CancelledError）都尝试解冻，避免冻结悬挂。解冻本身被包裹在
        # try/except 中：若解冻也失败（如 Redis 锁异常、事件循环关闭竞态），仅记录
        # warning 不再抛出——否则会掩盖 operation 抛出的原始异常。账本幂等 + Task 7
        # 的 Celery Beat 补偿任务会兜底清理悬挂冻结，因此吞掉解冻异常是可恢复的。
        try:
            await unfreeze_frozen(db, user_id=user_id, billing_id=frozen.billing_id, created_by=user_id)
        except Exception:
            logger.warning(
                "unfreeze failed during billed operation cleanup; Celery Beat 补偿(Task 7)将兜底",
                exc_info=True,
            )
        raise
    await consume_frozen(db, user_id=user_id, billing_id=frozen.billing_id, created_by=user_id)
    return result


async def settle_task_billing_async(task_id: str) -> None:
    """异步上下文内直接结算：读取任务终态并消费/解冻冻结积分。

    为什么存在：
        merge/variant（`run_merge_task` / `run_variant_task`）通过 `asyncio.create_task`
        在**已运行的事件循环**内执行，不能调用 `asyncio.run(...)`（会抛
        `RuntimeError: asyncio.run() cannot be called from a running event loop`）。
        本函数是「异步侧结算核心」，供这些进程内任务在每个终态分支直接 `await`。

    设计要点：
    - **单一 async 会话**：开一个 `async_session_maker()` 会话，读任务行后立即在同一会话内
      调 `consume_frozen` / `unfreeze_frozen`（账本内部自行 COMMIT）。早退（任务不存在 /
        `billing_id is None` / 非终态）发生在调用账本之前，避免无谓开事务。
    - **幂等**：账本 `consume_frozen` / `unfreeze_frozen` 自身幂等（同 billing_id 重复只入账
      一次）；终态互斥（已扣减不可再解冻）由账本保证。
    - **零行为变更**：`billing_id is None`（存量任务或未计费任务）直接返回。
    - **非终态跳过**：仅 `succeeded`/`failed`/`cancelled` 触发结算。
    - **失败不阻断**：`BillingStateError`（幂等/互斥冲突）视为良性竞争记 warning 后吞掉；
      其它异常记 exception 后吞掉（不阻断任务流程），Task 7 的 Celery Beat 补偿兜底。

    Args:
        task_id: 任务行 ID。

    由 `run_merge_task` / `run_variant_task` 终态点（成功/失败/取消共 5 个分支）直接 `await`。
    """
    from app.models.task import GenerationTask, GenerationTaskStatus
    from app.services.points import BillingStateError, consume_frozen, unfreeze_frozen

    async with async_session_maker() as db:
        row = await db.get(GenerationTask, task_id)
        if row is None or not row.billing_id:
            return  # 任务不存在或未计费：零行为变更
        status = row.status
        billing_id = row.billing_id
        user_id = row.user_id

        # 仅终态结算（status 列存的是枚举值字符串，GenerationTaskStatus 是 str Enum）
        if status not in (
            GenerationTaskStatus.succeeded.value,
            GenerationTaskStatus.failed.value,
            GenerationTaskStatus.cancelled.value,
        ):
            return  # 非终态（pending/running/streaming）不结算

        try:
            if status == GenerationTaskStatus.succeeded.value:
                # consume_frozen / unfreeze_frozen 内部自行 COMMIT。
                await consume_frozen(db, user_id=user_id, billing_id=billing_id, created_by="system")
            else:
                await unfreeze_frozen(
                    db, user_id=user_id, billing_id=billing_id, remark=f"task {status}", created_by="system"
                )
        except BillingStateError:
            # 幂等/互斥冲突（已结算过）：良性 mutex race，记 warning 后吞掉，不阻断任务流程。
            logger.warning(
                "settle idempotent skip for task_id=%s billing_id=%s status=%s",
                task_id,
                billing_id,
                status,
            )
        except Exception:  # noqa: BLE001 - 其它异常：记日志后吞掉，Task 7 补偿兜底
            logger.exception(
                "settle_task_billing_async failed for task_id=%s billing_id=%s",
                task_id,
                billing_id,
            )


def settle_task_billing_sync(task_id: str) -> None:
    """Celery worker 统一结算钩子（同步入口）：委托异步核心 `settle_task_billing_async`。

    为什么存在：
        Celery worker 在同步上下文运行（`run_task_celery` 的 finally），需要一个同步入口
        桥接到异步账本。本函数是「同步侧薄包装」：用 `asyncio.run` 启动事件循环驱动
        异步核心（与 `AbstractAsyncDelegatingExecutor.run` 同款桥接模式）。

    设计要点：
    - **薄包装**：所有读任务行 / 终态判定 / 账本调用逻辑都收敛到
      `settle_task_billing_async`，本函数不再重复 status-reading 逻辑，避免双份维护。
    - **失败不阻断**：`asyncio.run` 抛出的任何异常（含异步核心内部已吞掉的之外）仅记录
      日志后吞掉，不阻断 Celery 任务流程；Task 7 的 Celery Beat 补偿兜底。
    - **每次调用前重建 async DB runtime**：`AbstractAsyncDelegatingExecutor.run` 在
      `asyncio.run` 完成后会 `close_db()`（dispose engine pool）。dispose 只关闭连接，
      但 pool 对象内部的 asyncio 原语（Queue/Lock）仍绑定到已关闭的旧 event loop。
      若不重建，新的 `asyncio.run` 会在旧 loop 的 pool 上操作，触发
      "Future attached to a different loop"。`reset_db_runtime()` 创建全新 engine/pool，
      保证新 event loop 的 asyncio 原语与 pool 绑定一致。

    由 `app/tasks/execute_task.py::run_task_celery` 的 `finally` 调用，确保任务无论成功/失败/
    取消都会触发结算。

    **不要在 asyncio.create_task 启动的任务里调用本函数**：会触发
    `asyncio.run() cannot be called from a running event loop`。进程内任务（merge/variant）
    请直接 `await settle_task_billing_async(task_id)`。
    """
    from app.core.db import reset_db_runtime

    try:
        reset_db_runtime()
        asyncio.run(settle_task_billing_async(task_id))
    except Exception:  # noqa: BLE001 - 结算失败不阻断任务流程，补偿任务(Task 7)兜底
        logger.exception(
            "settle_task_billing_sync failed for task_id=%s", task_id
        )


async def quote_points(
    db: AsyncSession,
    *,
    user_id: str,
    business_type: str,
    category: ModelCategoryKey,
    model_id: str | None = None,
    duration_seconds: int | None = None,
    resolution: str | None = None,
    resolution_profile: str | None = None,
    generation_count: int = 1,
) -> PointsQuoteResponse:
    """试算：解析模型 → 计价 → 查余额 → 签发 quote_token。

    - 显式 `model_id`：先按 id 取 Model，校验归属（`model.user_id == user_id`）与类别匹配。
    - 默认模型：调用 `get_default_model_by_category`，无默认配置时让其抛 503 HTTPException
      （属配置错误，由通用 HTTPException 处理器兜底即可）。
    - 计价参数（duration_seconds/resolution）写入 params_hash 绑定到 quote_token，
      防止客户端在确认扣费时篡改影响价格的入参。
    """
    using_default_model = model_id is None

    if not using_default_model:
        # 显式模型：手动按 id 取并做归属校验（resolver 不校验归属）。
        model = await db.get(Model, model_id)
        if model is None:
            # 模型不存在：交由通用 404 处理（resolver 风格一致）。
            from fastapi import HTTPException, status
            from app.services.common import entity_not_found

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Model")
            ) from None
        if model.user_id != user_id:
            raise build_model_not_owned_error(model_id=model_id, user_id=user_id)
        if model.category != category:
            raise PointsDomainError(
                code="MODEL_CATEGORY_MISMATCH",
                message=f"model {model_id} category={model.category} != requested={category}",
                status_code=400,
                data={"model_id": model_id, "model_category": str(model.category), "requested_category": str(category)},
            )
    else:
        # 默认模型解析：无默认配置会抛 503（配置错误）。
        model = await get_default_model_by_category(db, category, user_id=user_id)

    # 计价（视频缺时长/分辨率、不支持分辨率由 pricing 抛 ValueError/UnsupportedResolutionError）。
    required_points = calculate_points(
        category=category,
        unit_points=model.unit_points,
        duration_seconds=duration_seconds,
        resolution=resolution,
        resolution_profile=resolution_profile,
        generation_count=generation_count,
    )

    # 余额/可用额度（纯读取，不加锁）。
    pts = await get_points(db, user_id=user_id)
    available = pts.balance - pts.frozen
    sufficient = available >= required_points

    # 绑定影响价格的参数到 quote_token，防篡改。
    params_hash = hash_quote_params(
        {
            "category": str(category),
            "duration_seconds": duration_seconds,
            "resolution": resolution,
            "resolution_profile": resolution_profile,
            "generation_count": generation_count,
        }
    )
    quote_token = create_quote_token(
        QuoteClaims(
            user_id=user_id,
            business_type=business_type,
            model_id=model.id,
            params_hash=params_hash,
            required_points=required_points,
        )
    )

    return PointsQuoteResponse(
        resolved_model_id=model.id,
        resolved_model_name=model.name,
        using_default_model=using_default_model,
        required_points=required_points,
        available_points=available,
        sufficient=sufficient,
        quote_token=quote_token,
    )


def to_summary(balance: int, frozen: int) -> PointsSummaryRead:
    """由 balance/frozen 构造账户摘要 DTO（available = balance - frozen）。"""
    return PointsSummaryRead(balance=balance, frozen=frozen, available=balance - frozen)


async def list_user_transactions(
    db: AsyncSession,
    *,
    user_id: str,
    tx_type: str | None = None,
    business_type: str | None = None,
    billing_id: str | None = None,
    transaction_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PointTransaction], int]:
    """分页查询某用户积分流水，按 created_at 倒序。

    过滤项：type（流水类型枚举值字符串）、business_type、billing_id、transaction_id（精确匹配）。
    返回 (items, total)。
    """
    stmt = select(PointTransaction).where(PointTransaction.user_id == user_id)
    count_stmt = select(func.count()).select_from(PointTransaction).where(PointTransaction.user_id == user_id)

    if tx_type is not None:
        # 严格校验 type 值必须是合法的流水类型枚举值。非法值直接抛 ValueError，
        # 由上层路由转化为 422，避免静默退化成「永远查不到结果」的误导性空列表。
        type_filter = PointTransactionType(tx_type)
        stmt = stmt.where(PointTransaction.type == type_filter)
        count_stmt = count_stmt.where(PointTransaction.type == type_filter)
    if business_type is not None:
        stmt = stmt.where(PointTransaction.business_type == business_type)
        count_stmt = count_stmt.where(PointTransaction.business_type == business_type)
    if billing_id is not None:
        stmt = stmt.where(PointTransaction.billing_id == billing_id)
        count_stmt = count_stmt.where(PointTransaction.billing_id == billing_id)
    if transaction_id is not None:
        stmt = stmt.where(PointTransaction.id == transaction_id)
        count_stmt = count_stmt.where(PointTransaction.id == transaction_id)

    total = int((await db.scalar(count_stmt)) or 0)
    stmt = (
        stmt.order_by(PointTransaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await db.execute(stmt)).scalars().all())
    return items, total


async def list_grouped_transactions(
    db: AsyncSession,
    *,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    cascade_group_id: str | None = None,
    billing_id: str | None = None,
    transaction_id: str | None = None,
    simple_page: int = 1,
    simple_page_size: int = 20,
) -> tuple[list[dict], int, str | None, list[PointTransaction], int]:
    """按 cascade_group_id 聚合分组，按组最早 created_at 倒序，按组分页。

    返回 (groups, total_groups, matched_transaction_id, simple_txns)，每组包含多个 billing_id 生命周期。
    cascade_group_id / billing_id / transaction_id 为搜索参数，由搜索解析逻辑统一解析为
    resolved_cascade_group_id 后过滤；transaction_id 搜索时回传 matched_transaction_id。
    业务逻辑：
    - 同一 cascade_group_id 的所有 point_transactions 归为一组
    - 组内按 billing_id 再分组（即单据生命周期）
    - 每个单据的 status 由该 billing_id 下的事件推断：
      - 有 consume → "settled"
      - 有 unfreeze → "refunded"
      - 仅 freeze → "frozen"
    - total_net = 组内所有 consume 金额之和（实际从余额扣出的净额）
    """
    # ── 搜索参数解析：将 billing_id / transaction_id 解析为 cascade_group_id ──────
    matched_transaction_id: str | None = None
    resolved_cascade_group_id: str | None = cascade_group_id

    if transaction_id is not None:
        row = (await db.execute(
            select(PointTransaction.cascade_group_id, PointTransaction.id)
            .where(
                PointTransaction.id == transaction_id,
                PointTransaction.user_id == user_id,
            )
            .limit(1)
        )).first()
        if row is None or row[0] is None:
            return [], 0, None, [], 0

        resolved_cascade_group_id = row[0]
        matched_transaction_id = row[1]

    elif billing_id is not None:
        resolved_cascade_group_id = await db.scalar(
            select(PointTransaction.cascade_group_id)
            .where(
                PointTransaction.billing_id == billing_id,
                PointTransaction.user_id == user_id,
            )
            .limit(1)
        )
        if resolved_cascade_group_id is None:
            return [], 0, None, [], 0

    # 1) 查询当前页的 cascade_group_id 列表（去重、按最早时间倒序）
    base_where = [
        PointTransaction.user_id == user_id,
        PointTransaction.cascade_group_id.isnot(None),
    ]
    if resolved_cascade_group_id is not None:
        base_where.append(PointTransaction.cascade_group_id == resolved_cascade_group_id)

    group_subq = (
        select(
            PointTransaction.cascade_group_id,
            func.min(PointTransaction.created_at).label("group_created_at"),
        )
        .where(*base_where)
        .group_by(PointTransaction.cascade_group_id)
        .order_by(text("group_created_at desc"))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .subquery()
    )

    total = await db.scalar(
        select(func.count(func.distinct(PointTransaction.cascade_group_id)))
        .where(*base_where)
    ) or 0

    group_ids = [r[0] for r in (await db.execute(select(group_subq.c.cascade_group_id))).all()]

    # 2) 一次性拉取所有匹配流水（仅含已分组的 cascade 行，不含 NULL 孤儿）
    all_txs: list[PointTransaction] = []
    if group_ids:
        txs = (
            (await db.execute(
                select(PointTransaction)
                .where(
                    PointTransaction.user_id == user_id,
                    PointTransaction.cascade_group_id.in_(group_ids),
                )
                .order_by(PointTransaction.created_at.asc())
            ))
            .scalars()
            .all()
        )
        all_txs.extend(txs)

    # 3) 组装分组结构
    groups_map: dict[str, list[PointTransaction]] = OrderedDict()
    for tx in all_txs:
        key = tx.cascade_group_id or tx.billing_id or tx.id
        groups_map.setdefault(key, []).append(tx)

    result = []
    for gid, txs in groups_map.items():
        billings_map: dict[str, list[PointTransaction]] = OrderedDict()
        for tx in txs:
            bid = tx.billing_id or tx.id
            billings_map.setdefault(bid, []).append(tx)

        billings = []
        for bid, events in billings_map.items():
            freeze_amt = sum(e.amount for e in events if e.type == PointTransactionType.freeze)
            consume_amt = sum(e.amount for e in events if e.type == PointTransactionType.consume)
            has_consume = any(e.type == PointTransactionType.consume for e in events)
            has_unfreeze = any(e.type == PointTransactionType.unfreeze for e in events)
            status = "settled" if has_consume else ("refunded" if has_unfreeze else "frozen")
            model_id = next((e.model_id for e in events if e.model_id), None)
            bt = next((e.business_type for e in events if e.business_type), None)
            # 备注/操作人/时间取冻结事件（首笔），无冻结时退而取任意一笔
            freeze_event = next((e for e in events if e.type == PointTransactionType.freeze), events[0] if events else None)
            remark = freeze_event.remark if freeze_event else None
            created_by = freeze_event.created_by if freeze_event else None
            billing_created_at = freeze_event.created_at if freeze_event else None
            billings.append(dict(
                billing_id=bid, business_type=bt, model_id=model_id,
                status=status, frozen_amount=freeze_amt, net_amount=consume_amt,
                remark=remark, created_by=created_by, created_at=billing_created_at,
                events=[dict(id=e.id, type=e.type, amount=e.amount,
                             created_at=e.created_at, balance_after=e.balance_after,
                             frozen_after=e.frozen_after, remark=e.remark) for e in events],
            ))

        root_txs = [t for t in txs if t.cascade_group_id == t.billing_id] or txs
        bt = next((b["business_type"] for b in billings if b["business_type"]), None)
        result.append(dict(
            cascade_group_id=gid,
            business_type=bt,
            created_at=min(t.created_at for t in txs),
            total_net=sum(b["net_amount"] for b in billings),
            billings=billings,
        ))

    # group_ids 是按 min(created_at) DESC 排序的，result 需还原该顺序
    # （all_txs 按 ASC 加载导致 groups_map 插入顺序是从旧到新）
    gid_order = {gid: i for i, gid in enumerate(group_ids)}
    result.sort(key=lambda g: gid_order.get(g["cascade_group_id"], len(group_ids)))

    # ── 查询单笔流水（source="admin" 的充值/调整记录）─────
    simple_txns: list[PointTransaction] = []
    simple_total = 0
    if user_id:
        simple_base = (
            select(PointTransaction)
            .where(
                PointTransaction.user_id == user_id,
                PointTransaction.source == "admin",
            )
        )
        # 先算总数（用于分页器），再按页取数据
        simple_total = int(
            await db.scalar(
                select(func.count())
                .select_from(PointTransaction)
                .where(
                    PointTransaction.user_id == user_id,
                    PointTransaction.source == "admin",
                )
            )
            or 0
        )
        if simple_total > 0:
            rows = (await db.execute(
                simple_base.order_by(PointTransaction.created_at.desc())
                .offset((simple_page - 1) * simple_page_size)
                .limit(simple_page_size)
            )).scalars().all()
            simple_txns = list(rows)

    return result, total, matched_transaction_id, simple_txns, simple_total
