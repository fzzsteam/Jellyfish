from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.contracts.video_generation import VideoRatio, VideoResolution


class VideoGenerationTaskRequest(BaseModel):
    """视频生成任务请求体。

    显式 `model_id` 用于覆盖默认视频模型，保证工作室里的模型选择能进入实际任务。

    Task 5c：新增 `resolution`（720p/1080p）与 `quote_token`（积分试算凭证）。
    resolution 同时决定计费因子与各供应商生成的清晰度参数；quote_token 必须在
    任务创建前通过 `freeze_for_task` 完成冻结，确保「按 1080p 收费即按 1080p 生成」。
    """

    shot_id: str = Field(..., description="镜头 ID")
    model_id: str | None = Field(
        None,
        description="可选视频模型 ID（models.id）；不传则使用当前用户的默认视频模型",
    )
    reference_mode: Literal["first", "last", "key", "first_last", "first_last_key", "text_only"] = Field(
        ...,
        description="参考模式：first | last | key | first_last | first_last_key | text_only",
    )
    prompt: str | None = Field(
        None,
        description="视频提示词（text_only 必填；非文本模式可作为补充描述）",
    )
    images: list[str] = Field(
        default_factory=list,
        description="参考图 file_id 列表；帧模式需与 reference_mode 数量匹配，text_only 可携带默认资产参考图",
    )
    ratio: VideoRatio = Field(..., description="视频画幅比例，如 16:9 / 9:16")
    # seconds 由 ShotDetail.duration 自动确定；请求体不再接收覆盖值。
    resolution: VideoResolution = Field(..., description="视频清晰度档位（720p/1080p），决定计费与生成参数")
    quote_token: str = Field(..., description="积分试算凭证；任务创建前据此冻结积分，保证报价单据未被篡改")
