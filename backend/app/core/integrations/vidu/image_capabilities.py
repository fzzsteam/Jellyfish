"""Vidu 图片模型能力约束。

支持的模型：
- viduq2: 参考图生图（reference2image），最高 2K 分辨率

API 文档参数：
- aspect_ratio: "16:9" | "4:3" | "1:1" | "3:4" | "9:16"
- resolution: "1080P" | "2K" | "4K"
"""

from __future__ import annotations

from app.core.integrations.image_capabilities import ImageModelCapability

#: viduq2 默认能力
DEFAULT_VIDU_IMAGE_CAPABILITY = ImageModelCapability(
    supports_seed=True,
    supports_watermark=False,
    supported_ratios={"16:9", "4:3", "1:1", "3:4", "9:16"},
    # ratio_size_profiles 中的 "size" 字符串在 Vidu 语义下表示 resolution 档位
    ratio_size_profiles={
        "16:9": {"standard": "1080P", "high": "2K"},
        "4:3":  {"standard": "1080P", "high": "2K"},
        "1:1":  {"standard": "1080P", "high": "2K"},
        "3:4":  {"standard": "1080P", "high": "2K"},
        "9:16": {"standard": "1080P", "high": "2K"},
    },
    default_resolution_profile="high",
    min_n=1,
    max_n=1,  # reference2image 每次生成 1 张
)

_MODEL_CAPABILITY_OVERRIDES: dict[str, ImageModelCapability] = {}


def register_vidu_image_capability(*, model_prefix: str, capability: ImageModelCapability) -> None:
    """注册 Vidu 特定模型的能力覆盖。"""
    prefix = model_prefix.strip().lower()
    if not prefix:
        raise ValueError("model_prefix must not be empty")
    _MODEL_CAPABILITY_OVERRIDES[prefix] = capability


def clear_vidu_image_capability_overrides() -> None:
    """清空所有自定义覆盖，恢复为默认值。"""
    _MODEL_CAPABILITY_OVERRIDES.clear()


def resolve_vidu_image_capability(model: str | None) -> ImageModelCapability:
    """解析指定 Vidu 模型的图片生成能力。"""
    if not model:
        return DEFAULT_VIDU_IMAGE_CAPABILITY

    model_lower = model.strip().lower()
    for prefix, cap in _MODEL_CAPABILITY_OVERRIDES.items():
        if model_lower.startswith(prefix):
            return cap

    return DEFAULT_VIDU_IMAGE_CAPABILITY
