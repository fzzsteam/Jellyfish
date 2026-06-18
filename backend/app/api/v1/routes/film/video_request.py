from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.contracts.video_generation import VideoRatio


class VideoGenerationTaskRequest(BaseModel):
    """Request body for creating or previewing a shot video generation task."""

    shot_id: str = Field(..., description="Shot ID")
    reference_mode: Literal["first", "last", "key", "first_last", "first_last_key", "text_only"] = Field(
        ...,
        description="Reference mode: first | last | key | first_last | first_last_key | text_only",
    )
    prompt: str | None = Field(None, description="Video prompt; required for text_only after derivation")
    images: list[str] = Field(
        default_factory=list,
        description="Reference image file_id list; count must match reference_mode",
    )
    ratio: VideoRatio = Field(..., description="Video aspect ratio, e.g. 16:9 / 9:16")
    model_id: str | None = Field(
        None,
        description="Optional built-in generation model id, e.g. builtin:vidu:video:viduq3",
    )
    # Duration is resolved from ShotDetail.duration and is intentionally not user-overridable here.
