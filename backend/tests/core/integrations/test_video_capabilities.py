"""视频能力映射单测。"""

from __future__ import annotations

import pytest

from app.core.contracts.video_generation import VideoGenerationInput
from app.core.integrations.video_capabilities import (
    VideoModelCapability,
    clear_video_model_capability_overrides,
    infer_ratio_from_size,
    register_video_model_capability,
    resolve_video_capability,
    validate_video_options,
)


def test_infer_ratio_from_size_supports_ratio_and_resolution() -> None:
    assert infer_ratio_from_size("16:9") == "16:9"
    assert infer_ratio_from_size("1920x1080") == "16:9"
    assert infer_ratio_from_size("720x1280") == "9:16"
    assert infer_ratio_from_size("abc") is None


def test_resolve_video_capability_prefers_longest_prefix() -> None:
    clear_video_model_capability_overrides(provider="openai")
    register_video_model_capability(
        provider="openai",
        model_prefix="gpt-video",
        capability=VideoModelCapability(supports_seed=False),
    )
    register_video_model_capability(
        provider="openai",
        model_prefix="gpt-video-pro",
        capability=VideoModelCapability(supports_seed=True, supports_watermark=False),
    )
    try:
        cap = resolve_video_capability(provider="openai", model="gpt-video-pro-1")
        assert cap.supports_seed is True
        assert cap.supports_watermark is False
    finally:
        clear_video_model_capability_overrides(provider="openai")


def test_validate_video_options_rejects_capability_mismatch() -> None:
    clear_video_model_capability_overrides(provider="volcengine")
    register_video_model_capability(
        provider="volcengine",
        model_prefix="seedream-video",
        capability=VideoModelCapability(supports_seed=False),
    )
    try:
        inp = VideoGenerationInput(prompt="test", model="seedream-video-v1", ratio="16:9", seed=7)
        with pytest.raises(ValueError) as exc_info:
            validate_video_options(provider="volcengine", model=inp.model, input_=inp)
        assert "seed is not supported" in str(exc_info.value)
    finally:
        clear_video_model_capability_overrides(provider="volcengine")


def test_vidu_video_capability_rejects_watermark_and_allows_reference_ratio() -> None:
    cap = resolve_video_capability(provider="vidu", model="viduq3")
    assert cap.supports_watermark is False
    assert "3:4" in (cap.allowed_ratios or set())
    assert cap.default_ratio == "3:4"

    inp = VideoGenerationInput(prompt="test", model="viduq3", ratio="3:4", seconds=8, watermark=False)
    with pytest.raises(ValueError) as exc_info:
        validate_video_options(provider="vidu", model=inp.model, input_=inp)
    assert "watermark is not supported" in str(exc_info.value)


def test_vidu_mix_video_capability_uses_720p_mapping() -> None:
    cap = resolve_video_capability(provider="vidu", model="viduq3-mix")
    assert cap.supports_watermark is False
    assert cap.default_ratio == "3:4"
    assert cap.ratio_to_size_mapping
    assert cap.ratio_to_size_mapping["3:4"] == "720p"


def test_vidu_text_video_capability_uses_540p_mapping() -> None:
    cap = resolve_video_capability(provider="vidu", model="viduq3-pro")
    assert cap.supports_watermark is False
    assert cap.default_ratio == "4:3"
    assert cap.ratio_to_size_mapping
    assert cap.ratio_to_size_mapping["4:3"] == "540p"


def test_vidu_multiframe_video_capability_uses_1080p_mapping() -> None:
    cap = resolve_video_capability(provider="vidu", model="viduq2-turbo")
    assert cap.supports_watermark is False
    assert cap.default_ratio == "4:3"
    assert cap.ratio_to_size_mapping
    assert cap.ratio_to_size_mapping["4:3"] == "1080p"


def test_vidu_template_video_capability_uses_1080p_mapping() -> None:
    cap = resolve_video_capability(provider="vidu", model="template:hugging")
    assert cap.supports_watermark is False
    assert cap.default_ratio == "4:3"
    assert cap.ratio_to_size_mapping
    assert cap.ratio_to_size_mapping["4:3"] == "1080p"


def test_vidu_template_story_video_capability_uses_1080p_mapping() -> None:
    cap = resolve_video_capability(provider="vidu", model="story:choose_one_accept_value")
    assert cap.supports_watermark is False
    assert cap.default_ratio == "4:3"
    assert cap.ratio_to_size_mapping
    assert cap.ratio_to_size_mapping["4:3"] == "1080p"
