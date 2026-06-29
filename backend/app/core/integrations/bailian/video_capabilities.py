"""阿里百炼 (DashScope) 视频模型能力约束。

支持的视频生成模型：
- happyhorse-1.1-t2v (文本转视频，当前主要支持)
- 其他视频生成模型

参数规格参考（基于官方 API 文档和示例）：
https://help.aliyun.com/zh/model-studio/video-generation

HappyHorse-1.1-t2v 官方支持的参数：
- resolution: "720P" 或 "1080P"
- ratio: "16:9", "4:3", "1:1", "3:4", "9:16"
- duration: 3-15 秒
"""

from __future__ import annotations

from app.core.integrations.video_capabilities import VideoModelCapability

#: 百炼视频模型默认能力（适用于 HappyHorse-1.0-t2v 等模型）
# 基于 2026-05-29 官方 API 示例确认的规格
DEFAULT_BAILIAN_VIDEO_CAPABILITY = VideoModelCapability(
    supports_seed=True,
    supports_watermark=True,
    # 官方支持的比例（仅3种）
    allowed_ratios={
        "16:9",
        "4:3",
        "1:1",
        "3:4",
        "9:16",
    },
    default_ratio="16:9",
    # 使用 DashScope 的 resolution 字段格式（非 size）
    # ratio_to_size_mapping 已废弃，改用 resolution 字段
    ratio_to_size_mapping={
        "16:9": "720P",   # 高清横屏
        "4:3": "720P",
        "9:16": "720P",   # 高清竖屏
        "1:1": "720P",    # 高清方形
        "3:4": "720P",
    },
    min_seconds=3,
    max_seconds=15,
)

# 可选：480P 标清模式（节省成本或加快速度）
STANDARD_DEFINITION_CAPABILITY = VideoModelCapability(
    supports_seed=True,
    supports_watermark=True,
    allowed_ratios={"16:9", "9:16", "1:1"},
    default_ratio="16:9",
    ratio_to_size_mapping={
        "16:9": "480P",
        "9:16": "480P",
        "1:1": "480P",
    },
    min_seconds=2,
    max_seconds=10,
)


#: 模型特定覆盖配置（按前缀匹配）
_MODEL_CAPABILITY_OVERRIDES: dict[str, VideoModelCapability] = {}


def register_bailian_video_capability(*, model_prefix: str, capability: VideoModelCapability) -> None:
    """注册百炼特定视频模型的能力覆盖。

    Args:
        model_prefix: 模型名称前缀（如 "happyhorse" 匹配所有 happyhorse-* 模型）
        capability: 该模型的特定能力约束
    """
    prefix = model_prefix.strip().lower()
    _MODEL_CAPABILITY_OVERRIDES[prefix] = capability


def clear_bailian_video_capability_overrides() -> None:
    """清空所有自定义覆盖。"""
    _MODEL_CAPABILITY_OVERRIDES.clear()


def resolve_bailian_video_capability(model: str | None) -> VideoModelCapability:
    """解析指定百炼模型的视频生成能力。

    Args:
        model: 模型名称（如 "happyhorse-1.0-t2v"）

    Returns:
        VideoModelCapability: 该模型的能力约束配置

    如果没有找到特定覆盖，返回默认能力。
    """
    if not model:
        return DEFAULT_BAILIAN_VIDEO_CAPABILITY

    model_lower = model.strip().lower()

    for prefix, cap in _MODEL_CAPABILITY_OVERRIDES.items():
        if model_lower.startswith(prefix):
            return cap

    return DEFAULT_BAILIAN_VIDEO_CAPABILITY
