"""积分计价器（纯函数，无 IO）。

职责：
- 根据「模型类别 + 单价 + 时长 + 分辨率 + 生成次数」计算本次生成需扣减的积分。
- 用 `Decimal` + `ROUND_CEILING` 向上取整，杜绝因小数截断导致少扣。

为什么独立成模块：
- 计价规则是计费系统的核心，需要可被「试算」「扣费」「对账」等场景无副作用地复用，
  因此剥离为纯函数模块，便于单测与跨层调用。
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import Optional

from app.models.llm import ModelCategoryKey

# 图片分辨率系数（当前统一为 1.0；保留常量作为未来多档图片分辨率的扩展钩子）。
IMAGE_RESOLUTION_FACTOR: Decimal = Decimal("1.0")

# 视频分辨率系数表：键统一小写存储，便于做大小写无关匹配。
VIDEO_RESOLUTION_FACTORS: dict[str, Decimal] = {
    "720p": Decimal("1.0"),
    "1080p": Decimal("2.0"),
}


class UnsupportedResolutionError(Exception):
    """视频分辨率未在计价系数表中登记。"""


def _to_category(category: object) -> str:
    """将 `ModelCategoryKey` 枚举或字符串归一化为小写字符串。"""
    if isinstance(category, ModelCategoryKey):
        return category.value
    return str(category).lower()


def calculate_points(
    *,
    category: object,
    unit_points: int,
    duration_seconds: Optional[int],
    resolution: Optional[str],
    generation_count: int = 1,
) -> int:
    """计算一次生成请求需扣减的积分总数。

    入参语义：
    - `category`: 模型类别（text/image/video，可传 `ModelCategoryKey` 或字符串）。
    - `unit_points`: 单次生成的「基础单价」积分，必须为非负整数。
    - `duration_seconds`: 视频时长（秒），视频类别必填且必须为正整数；文本/图片忽略。
    - `resolution`: 分辨率标签，视频必填（大小写不敏感）；文本/图片忽略。
    - `generation_count`: 生成次数，当前仅支持 1（多轮生成能力后续任务再放开）。

    返回：扣减积分（Python int，向上取整）。

    异常：
    - `ValueError`: 单价/次数/时长非法。
    - `UnsupportedResolutionError`: 视频分辨率未登记。
    """
    if not isinstance(unit_points, int) or isinstance(unit_points, bool):
        raise ValueError("unit_points must be an int")
    if unit_points < 0:
        raise ValueError("unit_points must be >= 0")
    if generation_count != 1:
        raise ValueError("generation_count must be 1 (multi-generation not supported yet)")

    category_key = _to_category(category)

    if category_key in ("text", "image"):
        # 文本/图片：单价即总价，分辨率与时长不参与计价。
        base = Decimal(unit_points) * IMAGE_RESOLUTION_FACTOR
        return int(base.quantize(Decimal("1"), rounding=ROUND_CEILING))

    if category_key == "video":
        if not isinstance(duration_seconds, int) or isinstance(duration_seconds, bool):
            raise ValueError("duration_seconds must be a positive int for video")
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be a positive int for video")
        if not resolution:
            raise ValueError("resolution is required for video")
        factor = VIDEO_RESOLUTION_FACTORS.get(resolution.lower())
        if factor is None:
            raise UnsupportedResolutionError(f"unsupported video resolution: {resolution!r}")
        total = (
            Decimal(unit_points)
            * Decimal(duration_seconds)
            * factor
            * Decimal(generation_count)
        )
        return int(total.quantize(Decimal("1"), rounding=ROUND_CEILING))

    raise ValueError(f"unsupported category: {category!r}")
