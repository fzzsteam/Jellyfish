"""阿里百炼 (DashScope) 图片模型能力约束。

支持的图片生成模型：
- wanx-v1 (通义万相 v1)
- wanx2.1-t2i-turbo (通义万相 2.1 加速版)
- wanx2.1-t2i-plus (通义万相 2.1 标准版)
- wan2.7-image-pro (最新图像生成模型)

尺寸规格参考：
https://help.aliyun.com/zh/model-studio/getting-started/models#8e549b8f3
"""

from __future__ import annotations

from app.core.integrations.image_capabilities import ImageModelCapability

#: 百炼图片模型默认能力（适用于大多数 wanx/wan2.x 模型）
DEFAULT_BAILIAN_IMAGE_CAPABILITY = ImageModelCapability(
    supports_seed=True,
    supports_watermark=False,  # DashScope 默认无水印选项或由平台控制
    supported_ratios={
        "1:1",       # 正方形 (1024x1024 / 1536x1536)
        "4:3",      # 横屏 (1152x864 / 1536x1152)
        "3:4",      # 竖屏 (864x1152 / 1152x1536)
        "16:9",     # 宽屏 (1344x768)
        "9:16",     # 手机竖屏 (768x1344)
        "3:2",      # 摄影 (1440x960)
        "2:3",      # 人像 (960x1440)
    },
    default_resolution_profile="standard",
    # 注意：DashScope 原生 API 使用 * 分隔尺寸（如 "1024*1024"），而非 OpenAI 的 "1024x1024"
    ratio_size_profiles={
        "1:1": {"standard": "1024*1024", "high": "1536*1536", "2K": "2048*2048"},
        "4:3": {"standard": "1152*864", "high": "1536*1152"},
        "3:4": {"standard": "864*1152", "high": "1152*1536"},
        "16:9": {"standard": "1344*768"},
        "9:16": {"standard": "768*1344"},
        "3:2": {"standard": "1440*960"},
        "2:3": {"standard": "960*1440"},
    },
    min_n=1,
    max_n=4,  # DashScope 通常支持最多 4 张并发
)

#: 模型特定覆盖_CONFIG
_MODEL_CAPABILITY_OVERRIDES: dict[str, ImageModelCapability] = {}


def register_bailian_image_capability(*, model_prefix: str, capability: ImageModelCapability) -> None:
    """注册百炼特定模型的能力覆盖。"""
    prefix = model_prefix.strip().lower()
    _MODEL_CAPABILITY_OVERRIDES[prefix] = capability


def clear_bailian_image_capability_overrides() -> None:
    """清空所有自定义覆盖，恢复为默认值。"""
    _MODEL_CAPABILITY_OVERRIDES.clear()


def resolve_bailian_image_capability(model: str | None) -> ImageModelCapability:
    """解析指定百炼模型的图片生成能力。

    Args:
        model: 模型名称（如 'wanx-v1', 'wan2.7-image-pro' 等），None 表示使用默认

    Returns:
        该模型对应的能力约束对象
    """
    if not model:
        return DEFAULT_BAILIAN_IMAGE_CAPABILITY

    model_lower = model.strip().lower()

    # 查找是否有精确匹配或前缀匹配的覆盖
    for prefix, cap in _MODEL_CAPABILITY_OVERRIDES.items():
        if model_lower.startswith(prefix):
            return cap

    # 返回默认能力
    return DEFAULT_BAILIAN_IMAGE_CAPABILITY
