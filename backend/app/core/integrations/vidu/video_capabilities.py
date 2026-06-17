"""Vidu video model capability constraints."""

from __future__ import annotations

from app.core.integrations.video_capabilities import VideoModelCapability

# Vidu subject reference2video currently uses viduq3 in the official examples.
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
    max_seconds=8,
)

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
    max_seconds=8,
)

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
    max_seconds=8,
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
