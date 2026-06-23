"""Project style profile registry.

The project style enum tells the database what was selected. A style profile
adds the creative instructions that generation services should pass to agents.
Profiles are stored as Jellyfish-owned JSON data so the prompt layer can grow
without copying another project's skill-directory implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from app.models.types import ProjectStyle, ProjectVisualStyle


PROFILE_DIR = Path(__file__).resolve().parents[2] / "style_profiles" / "video_styles"


@dataclass(frozen=True)
class StyleProfile:
    id: str
    visual_style: ProjectVisualStyle
    style: ProjectStyle
    label: str
    category: str
    description: str
    frame_prompt_guidance: str
    video_prompt_guidance: str
    asset_prompt_guidance: str
    director_guidance: str
    order: int = 100


def _read_profile_file(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("profiles", [])
    if not isinstance(raw, list):
        raise ValueError(f"style profile file must contain a list: {path}")
    return [item for item in raw if isinstance(item, dict)]


def _profile_from_dict(data: dict[str, Any]) -> StyleProfile:
    visual_style = ProjectVisualStyle(str(data["visual_style"]))
    style = ProjectStyle(str(data["style"]))
    label = str(data.get("label") or style.value)
    return StyleProfile(
        id=str(data.get("id") or f"{visual_style.name}:{style.name}"),
        visual_style=visual_style,
        style=style,
        label=label,
        category=str(data.get("category") or visual_style.value),
        description=str(data.get("description") or ""),
        frame_prompt_guidance=str(data.get("frame_prompt_guidance") or ""),
        video_prompt_guidance=str(data.get("video_prompt_guidance") or ""),
        asset_prompt_guidance=str(data.get("asset_prompt_guidance") or ""),
        director_guidance=str(data.get("director_guidance") or ""),
        order=int(data.get("order") or 100),
    )


def _coerce_visual_style(value: Any) -> ProjectVisualStyle:
    return ProjectVisualStyle(getattr(value, "value", value))


def _coerce_project_style(value: Any) -> ProjectStyle:
    return ProjectStyle(getattr(value, "value", value))


@lru_cache(maxsize=1)
def list_style_profiles() -> tuple[StyleProfile, ...]:
    profiles: list[StyleProfile] = []
    for path in sorted(PROFILE_DIR.glob("*.json")):
        for item in _read_profile_file(path):
            profiles.append(_profile_from_dict(item))
    profiles.sort(key=lambda item: (item.visual_style.value, item.order, item.label))
    return tuple(profiles)


def get_style_profile(visual_style: ProjectVisualStyle | str, style: ProjectStyle | str) -> StyleProfile:
    visual_style = _coerce_visual_style(visual_style)
    style = _coerce_project_style(style)
    for profile in list_style_profiles():
        if profile.visual_style == visual_style and profile.style == style:
            return profile
    raise KeyError(f"style profile not found: visual_style={visual_style.value}, style={style.value}")


def find_style_profile(visual_style: ProjectVisualStyle | str, style: ProjectStyle | str) -> StyleProfile | None:
    try:
        return get_style_profile(visual_style, style)
    except (KeyError, ValueError):
        return None


def style_profile_guidance_text(profile: StyleProfile | None) -> str:
    if profile is None:
        return ""
    sections = [
        ("镜头画面", profile.frame_prompt_guidance),
        ("视频运动", profile.video_prompt_guidance),
        ("资产设定", profile.asset_prompt_guidance),
        ("导演执行", profile.director_guidance),
    ]
    return "\n".join(f"{title}：{text}" for title, text in sections if text).strip()
