from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.dependencies import get_current_user, get_db
from app.models.llm import ModelCategoryKey
from app.models.task_links import GenerationTaskLink
from app.models.user import User
from app.schemas.common import ApiResponse, created_response
from app.services.film.shot_frame_prompt_tasks import (
    build_run_args as build_shot_frame_prompt_run_args,
    normalize_frame_type,
    relation_type_for_frame,
)
from app.services.points import unfreeze_frozen
from app.services.points.billing import freeze_for_task
from app.services.studio.shot_status import mark_shot_generating
from app.tasks.execute_task import enqueue_task_execution

from .common import (
    ShotFramePromptRequest,
    TaskCreated,
    _CreateOnlyTask,
)
router = APIRouter()


@router.post(
    "/tasks/shot-frame-prompts",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="镜头分镜帧提示词生成（任务版）",
)
async def create_shot_frame_prompt_task(
    body: ShotFramePromptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[TaskCreated]:
    frame_type = normalize_frame_type(body.frame_type)
    relation_type = relation_type_for_frame(frame_type)

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    run_args = await build_shot_frame_prompt_run_args(
        db,
        shot_id=body.shot_id,
        frame_type=frame_type,
    )

    # 分镜帧提示词生成走真实文本 LLM（最多 2 次调用），下单前按 quote_token 冻结积分。
    # freeze_for_task 内部会 COMMIT；后续 tm.create / 落库失败必须显式 unfreeze 兜底，
    # 否则冻结会悬挂直至 Celery Beat 补偿。model_id=None 表示沿用 token 内绑定的文本模型。
    frozen = await freeze_for_task(
        db,
        user_id=current_user.id,
        quote_token=body.quote_token,
        business_type="shot_frame_prompt",
        category=ModelCategoryKey.text,
        model_id=None,
    )
    try:
        task_record = await tm.create(
            task=_CreateOnlyTask(),
            mode=DeliveryMode.async_polling,
            user_id=current_user.id,
            task_kind="shot_frame_prompt",
            run_args=run_args,
            billing_id=frozen.billing_id,
        )
        db.add(
            GenerationTaskLink(
                task_id=task_record.id,
                resource_type="prompt",
                relation_type=relation_type,
                relation_entity_id=body.shot_id,
            )
        )
        await mark_shot_generating(db, shot_id=body.shot_id)
        await db.commit()
    except Exception:
        # 任务创建/入库失败：按 5a 契约回滚冻结，避免冻结悬挂。
        await unfreeze_frozen(db, user_id=current_user.id, billing_id=frozen.billing_id, created_by=current_user.id)
        raise

    enqueue_task_execution(task_record.id)
    return created_response(TaskCreated(task_id=task_record.id))
