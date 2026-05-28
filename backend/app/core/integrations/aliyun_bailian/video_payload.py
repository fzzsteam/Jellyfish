"""阿里百炼 DashScope 视频：请求体构建（原生 API 格式）。

将统一的 :class:`VideoGenerationInput` 映射为 DashScope 原生视频合成请求体。

API 参考（happyhorse-1.0-i2v 官方 curl 示例）::

    POST https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis
    Headers:
      X-DashScope-Async: enable
      Authorization: Bearer {api_key}
      Content-Type: application/json

    Body::

        {
          "model": "happyhorse-1.0-i2v",
          "input": {
            "prompt": "...",
            "media": [
              {"type": "first_frame", "url": "<可访问的图片URL>"}
            ]
          },
          "parameters": {
            "resolution": "720P",
            "duration": 5
          }
        }

关键要点：
- 参考帧通过 ``input.media[]`` 数组传递（不是 ref_image_url）
- resolution 使用字符串档位：``"720P"`` / ``"1080P"``
- 必须携带 ``X-DashScope-Async: enable`` 头以启用异步任务模式
"""

from __future__ import annotations

from typing import Any

from app.core.contracts.video_generation import VideoGenerationInput, _strip_optional_b64


# 视频模型前缀映射（保留用于未来扩展）
# _HAPPYHORSE_PREFIXES = ("happyhorse",)
# _WANX_VIDEO_PREFIXES = ("wanx", "wan2")


# 比例 → DashScope 分辨率档位映射
_RATIO_TO_RESOLUTION = {
    "16:9": "720P",
    "9:16": "720P",
    "1:1": "720P",
    "3:4": "720P",
    "4:3": "720P",
}


def _resolve_video_api_model(input_: VideoGenerationInput) -> str:
    """根据模型名返回 DashScope API 支持的模型标识。"""
    model = (input_.model or "").strip()
    if not model:
        return "happyhorse-1.0-i2v"
    return model.strip()


def _ratio_to_resolution(ratio: str | None) -> str:
    """根据宽高比返回 DashScope 视频分辨率档位。"""
    if not ratio:
        return "720P"
    key = ratio.strip().replace(" ", "")
    return _RATIO_TO_RESOLUTION.get(key, "720P")


def _build_media_list(input_: VideoGenerationInput) -> list[dict[str, str]]:
    """构建 input.media 数组（参考帧列表）。

    DashScope 要求 media 元素使用可公开访问的 HTTP(S) URL，
    不支持 data: base64 内联数据。
    """
    media: list[dict[str, str]] = []

    ff = _strip_optional_b64(input_.first_frame_base64)
    if ff:
        # 如果是 Data URL 则跳过（DashScope 无法解析）
        if not ff.startswith("data:"):
            media.append({"type": "first_frame", "url": ff})

    lf = _strip_optional_b64(input_.last_frame_base64)
    if lf:
        if not lf.startswith("data:"):
            media.append({"type": "last_frame", "url": lf})

    kf = _strip_optional_b64(input_.key_frame_base64)
    if kf:
        if not kf.startswith("data:"):
            media.append({"type": "keyframe", "url": kf})

    return media


def build_synthesis_body(input_: VideoGenerationInput) -> dict[str, Any]:
    """构建 DashScope 原生视频合成请求体。

    对应 ``POST /api/v1/services/aigc/video-generation/video-synthesis``
    （注意：路径是 ``video-synthesis``，不是 ``synthesis``）。
    """
    prompt = (input_.prompt or "").strip()

    inp: dict[str, Any] = {}
    if prompt:
        inp["prompt"] = prompt

    # 参考帧：DashScope 使用 input.media[] 数组
    media = _build_media_list(input_)
    if media:
        inp["media"] = media
    else:
        # 诊断日志：帮助排查为什么 media 为空
        import logging as _logging
        _logger = _logging.getLogger(__name__)
        _logger.warning(
            "[aliyun-bailian-video] input.media is EMPTY — "
            "first_frame=%r last_frame=%r key_frame=%r "
            "(Data URLs are skipped; real HTTP URLs required for DashScope)",
            (input_.first_frame_base64 or "")[:80] if input_.first_frame_base64 else None,
            (input_.last_frame_base64 or "")[:80] if input_.last_frame_base64 else None,
            (input_.key_frame_base64 or "")[:80] if input_.key_frame_base64 else None,
        )
        # 对于 i2v 模型（如 happyhorse-1.0-i2v），media 是必填字段
        # t2v 模型（如 happyhorse-1.0-t2v）不需要参考图，允许 media 为空
        model_lower = (input_.model or "").lower()
        is_i2v_model = "i2v" in model_lower
        if is_i2v_model:
            raise ValueError(
                "Aliyun Bailian i2v model (e.g. happyhorse) requires at least one reference frame image "
                "(first_frame), but none was provided. Please ensure the shot has associated reference "
                "frame images before generating video with an image-to-video model."
            )

    if not inp and not prompt:
        raise RuntimeError(
            "Aliyun Bailian video requires non-empty input (prompt and/or reference frames)"
        )

    body: dict[str, Any] = {
        "model": _resolve_video_api_model(input_),
        "input": inp,
        "parameters": {},
    }

    # --- parameters 区（扁平结构） ---
    params: dict[str, Any] = {}

    # 分辨率档位："720P" 或 "1080P"
    params["resolution"] = _ratio_to_resolution(input_.ratio)

    # 时长（秒）
    if input_.seconds is not None:
        params["duration"] = int(input_.seconds)

    # 种子
    if input_.seed is not None:
        params["seed"] = int(input_.seed)

    body["parameters"] = params

    return body


def build_async_headers(api_key: str) -> dict[str, str]:
    """构建视频合成请求所需的额外 HTTP 头。"""
    return {
        "X-DashScope-Async": "enable",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
