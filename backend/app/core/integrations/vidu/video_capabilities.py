"""Vidu video model capability constraints."""

from __future__ import annotations

from app.core.integrations.video_capabilities import VideoModelCapability

# viduq3: reference2video 主力模型，多机位人物一致性最优。文档：3-16s，540p/720p/1080p。
DEFAULT_VIDU_VIDEO_CAPABILITY = VideoModelCapability(
    supports_seed=True,
    supports_watermark=False,
    allowed_ratios={"16:9", "4:3", "1:1", "3:4", "9:16"},
    default_ratio="3:4",
    ratio_to_size_mapping={
        "16:9": "1080p",
        "4:3": "1080p",
        "1:1": "1080p",
        "3:4": "1080p",
        "9:16": "1080p",
    },
    min_seconds=1,
    max_seconds=16,
)

# viduq3-mix: reference2video 混合模式，使用 images 字段（非 subjects），720p/1080p，3-16s。
VIDU_MIX_VIDEO_CAPABILITY = VideoModelCapability(
    supports_seed=True,
    supports_watermark=False,
    allowed_ratios={"16:9", "4:3", "1:1", "3:4", "9:16"},
    default_ratio="3:4",
    ratio_to_size_mapping={
        "16:9": "720p",
        "4:3": "720p",
        "1:1": "720p",
        "3:4": "720p",
        "9:16": "720p",
    },
    min_seconds=1,
    max_seconds=16,
)

# viduq3-pro: text2video / img2video（首帧）专用，不支持 reference2video subjects。
# 文档：1-16s，540p/720p/1080p；成本比 viduq3 低，适合纯文字镜头。
VIDU_TEXT_VIDEO_CAPABILITY = VideoModelCapability(
    supports_seed=True,
    supports_watermark=False,
    allowed_ratios={"16:9", "4:3", "1:1", "3:4", "9:16"},
    default_ratio="4:3",
    ratio_to_size_mapping={
        "16:9": "540p",
        "4:3": "540p",
        "1:1": "540p",
        "3:4": "540p",
        "9:16": "540p",
    },
    min_seconds=1,
    max_seconds=16,
)

# viduq3-turbo: 速度最快，同时支持 reference2video（subjects）和 text/img/start-end2video。
# 文档：1-16s，540p/720p/1080p；作为参考图生成时默认 720p，兼顾速度与质量。
VIDU_TURBO_VIDEO_CAPABILITY = VideoModelCapability(
    supports_seed=True,
    supports_watermark=False,
    allowed_ratios={"16:9", "4:3", "1:1", "3:4", "9:16"},
    default_ratio="4:3",
    ratio_to_size_mapping={
        "16:9": "720p",
        "4:3": "720p",
        "1:1": "720p",
        "3:4": "720p",
        "9:16": "720p",
    },
    min_seconds=1,
    max_seconds=16,
)

VIDU_MULTIFRAME_VIDEO_CAPABILITY = VideoModelCapability(
    supports_seed=True,
    supports_watermark=False,
    allowed_ratios={"16:9", "4:3", "1:1", "3:4", "9:16"},
    default_ratio="4:3",
    ratio_to_size_mapping={
        "16:9": "1080p",
        "4:3": "1080p",
        "1:1": "1080p",
        "3:4": "1080p",
        "9:16": "1080p",
    },
    min_seconds=1,
    max_seconds=8,
)

VIDU_TEMPLATE_VIDEO_CAPABILITY = VideoModelCapability(
    supports_seed=True,
    supports_watermark=False,
    allowed_ratios={"16:9", "4:3", "1:1", "3:4", "9:16"},
    default_ratio="4:3",
    ratio_to_size_mapping={
        "16:9": "1080p",
        "4:3": "1080p",
        "1:1": "1080p",
        "3:4": "1080p",
        "9:16": "1080p",
    },
    min_seconds=1,
    max_seconds=8,
)

_MODEL_CAPABILITY_OVERRIDES: dict[str, VideoModelCapability] = {}


def register_vidu_video_capability(*, model_prefix: str, capability: VideoModelCapability) -> None:
    """Register a model-specific Vidu video capability override."""
    prefix = model_prefix.strip().lower()
    if not prefix:
        raise ValueError("model_prefix must not be empty")
    _MODEL_CAPABILITY_OVERRIDES[prefix] = capability


def clear_vidu_video_capability_overrides() -> None:
    """Clear custom Vidu video capability overrides."""
    _MODEL_CAPABILITY_OVERRIDES.clear()


def resolve_vidu_video_capability(model: str | None) -> VideoModelCapability:
    """Resolve Vidu video model capability by longest matching prefix."""
    if not model:
        return DEFAULT_VIDU_VIDEO_CAPABILITY

    model_lower = model.strip().lower()
    if model_lower.startswith("story:") or model_lower.startswith("template-story:"):
        return VIDU_TEMPLATE_VIDEO_CAPABILITY
    if model_lower.startswith("template:") or model_lower in {"hugging", "hug"}:
        return VIDU_TEMPLATE_VIDEO_CAPABILITY
    if model_lower.startswith("viduq2-turbo"):
        return VIDU_MULTIFRAME_VIDEO_CAPABILITY
    if model_lower.startswith("viduq3-mix"):
        return VIDU_MIX_VIDEO_CAPABILITY
    if model_lower.startswith("viduq3-turbo"):
        return VIDU_TURBO_VIDEO_CAPABILITY
    if model_lower.startswith("viduq3-pro"):
        return VIDU_TEXT_VIDEO_CAPABILITY

    matches = [
        (prefix, cap)
        for prefix, cap in _MODEL_CAPABILITY_OVERRIDES.items()
        if model_lower.startswith(prefix)
    ]
    if matches:
        return max(matches, key=lambda item: len(item[0]))[1]
    return DEFAULT_VIDU_VIDEO_CAPABILITY
