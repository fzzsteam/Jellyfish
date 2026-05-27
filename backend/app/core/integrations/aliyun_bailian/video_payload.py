"""阿里百炼 DashScope 视频：请求体构建与参考图映射。

将统一的 :class:`VideoGenerationInput` 映射为 DashScope 视频 API 请求体。
DashScope 兼容模式下视频创建接口参考 OpenAI Videos API 结构，
但字段命名和值格式需按 DashScope 文档调整。
"""

from __future__ import annotations

from typing import Any

from app.core.integrations.openai.video_payload import to_image_data_url
from app.core.integrations.aliyun_bailian.video_capabilities import validate_aliyun_bailian_video_options
from app.core.integrations.video_capabilities import derive_provider_size, resolve_effective_ratio
from app.core.contracts.video_generation import VideoGenerationInput, _strip_optional_b64


def build_content(input_: VideoGenerationInput) -> list[dict[str, Any]]:
    """构建 content 数组：文本提示词 + 参考帧图（首帧 / 尾帧 / 关键帧）。"""
    items: list[dict[str, Any]] = []
    prompt = (input_.prompt or "").strip()
    if prompt:
        items.append({"type": "text", "text": prompt})

    ff = _strip_optional_b64(input_.first_frame_base64)
    if ff:
        items.append({
            "type": "image_url",
            "role": "first_frame",
            "image_url": {"url": to_image_data_url(ff)},
        })

    lf = _strip_optional_b64(input_.last_frame_base64)
    if lf:
        items.append({
            "type": "image_url",
            "role": "last_frame",
            "image_url": {"url": to_image_data_url(lf)},
        })

    kf = _strip_optional_b64(input_.key_frame_base64)
    if kf:
        items.append({
            "type": "image_url",
            "role": "key_frame",
            "image_url": {"url": to_image_data_url(kf)},
        })

    return items


def build_create_task_body(input_: VideoGenerationInput) -> dict[str, Any]:
    """构建 DashScope 视频任务创建请求体。"""
    validate_aliyun_bailian_video_options(input_)
    content = build_content(input_)
    if not content:
        raise RuntimeError(
            "Aliyun Bailian video requires non-empty content (prompt and/or reference frames)"
        )

    effective_ratio = resolve_effective_ratio(input_)
    body: dict[str, Any] = {
        "model": input_.model or "video-generation",
        "input": {
            "prompt": input_.prompt or "",
        },
        "parameters": {},
    }

    # 参考帧图通过 input 传入
    ref_images = []
    ff = _strip_optional_b64(input_.first_frame_base64)
    if ff:
        ref_images.append({"image_url": to_image_data_url(ff), "role": "first_frame"})
    lf = _strip_optional_b64(input_.last_frame_base64)
    if lf:
        ref_images.append({"image_url": to_image_data_url(lf), "role": "last_frame"})
    kf = _strip_optional_b64(input_.key_frame_base64)
    if kf:
        ref_images.append({"image_url": to_image_data_url(kf), "role": "key_frame"})
    if ref_images:
        body["input"]["ref_images"] = ref_images

    # 参数区
    params: dict[str, Any] = {}
    if effective_ratio:
        params["aspect_ratio"] = effective_ratio
    size = derive_provider_size(provider="aliyun_bailian", model=input_.model, ratio=input_.ratio)
    if size:
        params["size"] = size
    if input_.seconds is not None:
        params["duration"] = int(input_.seconds)
    if input_.seed is not None:
        params["seed"] = int(input_.seed)
    if input_.watermark is not None:
        params["watermark"] = bool(input_.watermark)
    body["parameters"] = params

    return body
