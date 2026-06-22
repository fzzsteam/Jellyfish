"""积分计价器（纯函数）单测。

覆盖：
- 文本/图片/视频三类模型的积分计算
- 视频分辨率系数（720p=1.0、1080p=2.0）
- 未知分辨率抛 `UnsupportedResolutionError`
- 非法入参（负数单价、非 1 生成次数、非正时长）抛 `ValueError`
- 1080p 翻倍计价语义（`ROUND_CEILING` 在整数入参下与整数乘法等价，
  其防少扣保护作用需待未来引入小数系数时才会被触发）
"""

from __future__ import annotations

import pytest

from app.services.points import (
    UnsupportedResolutionError,
    calculate_points,
)


@pytest.mark.parametrize(
    ("category", "unit_points", "duration", "resolution", "expected"),
    [
        ("text", 12, None, None, 12),
        ("image", 20, None, None, 20),
        ("video", 10, 5, "720p", 50),
        ("video", 10, 5, "1080p", 100),
    ],
)
def test_calculate_points(category, unit_points, duration, resolution, expected):
    assert (
        calculate_points(
            category=category,
            unit_points=unit_points,
            duration_seconds=duration,
            resolution=resolution,
            generation_count=1,
        )
        == expected
    )


def test_unknown_video_resolution_is_rejected():
    with pytest.raises(UnsupportedResolutionError):
        calculate_points(
            category="video",
            unit_points=10,
            duration_seconds=5,
            resolution="4k",
        )


def test_video_requires_positive_duration():
    with pytest.raises(ValueError):
        calculate_points(
            category="video",
            unit_points=10,
            duration_seconds=0,
            resolution="720p",
        )


def test_negative_unit_points_rejected():
    with pytest.raises(ValueError):
        calculate_points(
            category="text",
            unit_points=-1,
            duration_seconds=None,
            resolution=None,
        )


def test_generation_count_must_be_one():
    with pytest.raises(ValueError):
        calculate_points(
            category="image",
            unit_points=10,
            duration_seconds=None,
            resolution=None,
            generation_count=2,
        )


def test_video_resolution_is_case_insensitive():
    assert (
        calculate_points(
            category="video",
            unit_points=10,
            duration_seconds=5,
            resolution="1080P",
        )
        == 100
    )


def test_video_cost_doubles_at_1080p():
    """1080p 视频计价应在 720p 基础上按系数 2.0 翻倍（3 * 2 * 2.0 = 12）。

    注：当前分辨率系数（1.0 / 2.0）与整数入参相乘不会产生小数，因此本用例并不触发
    `ROUND_CEILING` 分支；该向上取整逻辑是面向「未来引入小数系数」时的防少扣保护，
    在整数入参下与普通整数乘法等价。这里仅断言 1080p 的翻倍计价语义。
    """
    assert (
        calculate_points(
            category="video",
            unit_points=3,
            duration_seconds=2,
            resolution="1080p",  # 3 * 2 * 2.0 = 12.0
        )
        == 12
    )


def test_text_category_ignores_resolution_and_duration():
    assert (
        calculate_points(
            category="text",
            unit_points=7,
            duration_seconds=None,
            resolution=None,
        )
        == 7
    )
