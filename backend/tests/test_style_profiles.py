from __future__ import annotations

from app.models.types import ProjectStyle, ProjectVisualStyle
from app.services.studio import projects as project_service
from app.services.studio.style_profiles import (
    get_style_profile,
    list_style_profiles,
    style_profile_guidance_text,
)


def test_style_profiles_include_extra_visual_and_video_styles() -> None:
    profiles = list_style_profiles()

    assert get_style_profile(
        ProjectVisualStyle.live_action,
        ProjectStyle.real_people_suspense,
    ).video_prompt_guidance
    assert get_style_profile(
        ProjectVisualStyle.guofeng,
        ProjectStyle.guofeng_fantasy,
    ).director_guidance
    assert {profile.visual_style for profile in profiles} >= {
        ProjectVisualStyle.live_action,
        ProjectVisualStyle.anime,
        ProjectVisualStyle.guofeng,
        ProjectVisualStyle.stylized_3d,
    }


def test_project_style_options_are_built_from_profiles() -> None:
    mapping, defaults = project_service.build_project_style_options()

    assert ProjectStyle.real_people_suspense in mapping[ProjectVisualStyle.live_action]
    assert ProjectStyle.guofeng_fantasy in mapping[ProjectVisualStyle.guofeng]
    assert ProjectStyle.stylized_3d_fantasy in mapping[ProjectVisualStyle.stylized_3d]
    assert defaults[ProjectVisualStyle.live_action] == mapping[ProjectVisualStyle.live_action][0]


def test_style_profile_guidance_text_combines_generation_rules() -> None:
    profile = get_style_profile(ProjectVisualStyle.live_action, ProjectStyle.real_people_suspense)

    text = style_profile_guidance_text(profile)

    assert profile.frame_prompt_guidance in text
    assert profile.video_prompt_guidance in text
    assert profile.director_guidance in text
