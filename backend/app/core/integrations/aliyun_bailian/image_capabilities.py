"""阿里百炼图片能力声明与覆盖注册。

DashScope Wanx 系列模型支持的尺寸使用星号分隔（如 ``1024*1024``），
ratio-to-size 映射基于各模型官方文档定义的规格。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.integrations.image_capabilities import ImageModelCapability

if TYPE_CHECKING:
    from app.core.contracts.image_generation import ImageGenerationInput

# 阿里百炼 Wanx 模型支持的比例-尺寸映射（星号格式）
_ALIYUN_BAILIAN_RATIO_SIZE_PROFILES = {
    "1:1": {"standard": "1024*1024", "high": "1536*1536"},
    "16:9": {"standard": "1280*720", "high": "1920*1080"},
    "9:16": {"standard": "720*1280", "high": "1080*1920"},
    "4:3": {"standard": "960*1280", "high": "1440*1920"},
    "3:4": {"standard": "1280*960", "high": "1920*1440"},
    "3:2": {"standard": "1152*768", "high": "1728*1152"},
    "2:3": {"standard": "768*1152", "high": "1152*1728"},
}

_ALIYUN_BAILIAN_DEFAULT = ImageModelCapability(
    supports_seed=True,
    supports_watermark=True,
    allowed_sizes={
        size
        for profiles in _ALIYUN_BAILIAN_RATIO_SIZE_PROFILES.values()
        for size in profiles.values()
    },
    supported_ratios=set(_ALIYUN_BAILIAN_RATIO_SIZE_PROFILES.keys()),
    default_resolution_profile="standard",
    ratio_size_profiles=_ALIYUN_BAILIAN_RATIO_SIZE_PROFILES,
)

# key: 模型前缀（小写）
_ALIYUN_BAILIAN_MODEL_OVERRIDES: dict[str, ImageModelCapability] = {}


def register_aliyun_bailian_image_capability(*, model_prefix: str, capability: ImageModelCapability) -> None:
    prefix = model_prefix.strip().lower()
    if not prefix:
        raise ValueError("model_prefix must not be empty")
    _ALIYUN_BAILIAN_MODEL_OVERRIDES[prefix] = capability


def clear_aliyun_bailian_image_capability_overrides() -> None:
    _ALIYUN_BAILIAN_MODEL_OVERRIDES.clear()


def _pick_override(model: str | None) -> ImageModelCapability | None:
    if not model:
        return None
    value = model.strip().lower()
    if not value:
        return None
    for prefix, cap in sorted(
        _ALIYUN_BAILIAN_MODEL_OVERRIDES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if value.startswith(prefix):
            return cap
    return None


def resolve_aliyun_bailian_image_capability(model: str | None) -> ImageModelCapability:
    return _pick_override(model) or _ALIYUN_BAILIAN_DEFAULT


def validate_aliyun_bailian_image_options(input_: ImageGenerationInput) -> None:
    """阿里百炼能力校验入口（避免调用侧传 provider 字面量）。"""
    from app.core.contracts.image_generation import ImageGenerationInput
    from app.core.integrations.image_capabilities import validate_image_options

    assert isinstance(input_, ImageGenerationInput)
    validate_image_options(provider="aliyun_bailian", model=input_.model, input_=input_)
