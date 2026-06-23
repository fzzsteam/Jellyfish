from __future__ import annotations

from app.schemas.studio.shots import ShotPromptCameraInfo, ShotVideoPromptPackRead
from app.services.studio.shot_video_prompt_pack import _pack_variables


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
