from __future__ import annotations

from app.schemas.studio.shots import ShotPromptCameraInfo, ShotVideoPromptPackRead
from app.services.studio.shot_video_prompt_pack import (
    _fallback_video_prompt,
    _pack_variables,
    enrich_rendered_video_prompt,
)


def test_pack_variables_expose_style_profile_guidance() -> None:
    pack = ShotVideoPromptPackRead(
        shot_id="shot-1",
        title="测试镜头",
        script_excerpt="角色进入房间。",
        camera=ShotPromptCameraInfo(camera_shot="MS", angle="EYE_LEVEL", movement="STATIC", duration=4),
        visual_style="现实",
        style="真人悬疑",
        style_profile_guidance="镜头画面：低调光影；视频运动：克制推进。",
    )

    variables = _pack_variables(pack)

    assert variables["style_profile_guidance"] == "镜头画面：低调光影；视频运动：克制推进。"
    assert variables["pack"]["style_profile_guidance"] == "镜头画面：低调光影；视频运动：克制推进。"


def test_fallback_video_prompt_includes_style_profile_guidance() -> None:
    pack = ShotVideoPromptPackRead(
        shot_id="shot-1",
        title="测试镜头",
        script_excerpt="角色进入房间。",
        camera=ShotPromptCameraInfo(camera_shot="MS", angle="EYE_LEVEL", movement="STATIC", duration=4),
        visual_style="现实",
        style="真人悬疑",
        style_profile_guidance="镜头画面：低调光影；视频运动：克制推进。",
    )

    prompt = _fallback_video_prompt(pack)

    assert "项目风格档案：镜头画面：低调光影；视频运动：克制推进。" in prompt


def test_enrich_rendered_video_prompt_adds_style_profile_when_template_omits_it() -> None:
    pack = ShotVideoPromptPackRead(
        shot_id="shot-1",
        title="测试镜头",
        script_excerpt="角色进入房间。",
        action_beats=["角色回头"],
        camera=ShotPromptCameraInfo(camera_shot="MS", angle="EYE_LEVEL", movement="STATIC", duration=4),
        visual_style="现实",
        style="真人悬疑",
        style_profile_guidance="镜头画面：低调光影；视频运动：克制推进。",
    )

    prompt = enrich_rendered_video_prompt(rendered_prompt="镜头标题：测试镜头", pack=pack)

    assert "镜头标题：测试镜头" in prompt
    assert "项目风格档案：镜头画面：低调光影；视频运动：克制推进。" in prompt
    assert "动作节拍：角色回头" in prompt


def test_enrich_rendered_video_prompt_adds_style_profile_even_when_template_has_other_guidance() -> None:
    pack = ShotVideoPromptPackRead(
        shot_id="shot-1",
        title="测试镜头",
        script_excerpt="角色进入房间。",
        action_beats=["角色回头"],
        camera=ShotPromptCameraInfo(camera_shot="MS", angle="EYE_LEVEL", movement="STATIC", duration=4),
        visual_style="现实",
        style="真人悬疑",
        style_profile_guidance="镜头画面：低调光影；视频运动：克制推进。",
    )

    prompt = enrich_rendered_video_prompt(rendered_prompt="镜头标题：测试镜头\n连续性要求：保持轴线", pack=pack)

    assert "项目风格档案：镜头画面：低调光影；视频运动：克制推进。" in prompt
    assert prompt.count("连续性要求：") == 1
