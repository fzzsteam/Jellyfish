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
from typing import Any

from sqlalchemy import func, select
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
    duration_seconds: int | None = None,
    resolution: str | None = None,
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
            snapshot=snapshot,
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
                await consume_frozen(db, user_id=user_id, billing_id=billing_id)
            else:
                await unfreeze_frozen(
                    db, user_id=user_id, billing_id=billing_id, remark=f"task {status}"
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

    由 `app/tasks/execute_task.py::run_task_celery` 的 `finally` 调用，确保任务无论成功/失败/
    取消都会触发结算。

    **不要在 asyncio.create_task 启动的任务里调用本函数**：会触发
    `asyncio.run() cannot be called from a running event loop`。进程内任务（merge/variant）
    请直接 `await settle_task_billing_async(task_id)`。
    """
    try:
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
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PointTransaction], int]:
    """分页查询某用户积分流水，按 created_at 倒序。

    过滤项：type（流水类型枚举值字符串）、business_type、billing_id。
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

    total = int((await db.scalar(count_stmt)) or 0)
    stmt = (
        stmt.order_by(PointTransaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await db.execute(stmt)).scalars().all())
    return items, total
