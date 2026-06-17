"""Shared video generation capability constraints and helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.contracts.provider import ProviderKey
from app.core.contracts.video_generation import VideoGenerationInput, VideoRatio

ALLOWED_RATIOS = {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9"}
DEFAULT_RATIO_TO_SIZE_MAPPING: dict[str, str] = {
    "16:9": "1280x720",
    "4:3": "1024x768",
    "1:1": "1024x1024",
    "3:4": "768x1024",
    "9:16": "720x1280",
    "21:9": "1680x720",
}


@dataclass(frozen=True, slots=True)
class VideoModelCapability:
    """Provider/model capability settings used before submitting video tasks."""

    supports_seed: bool = True
    supports_watermark: bool = False
    allowed_ratios: set[str] | None = None
    default_ratio: str | None = None
    ratio_to_size_mapping: dict[str, str] | None = None
    min_seconds: int | None = 1
    max_seconds: int | None = None


def register_video_model_capability(
    *,
    provider: ProviderKey,
    model_prefix: str,
    capability: VideoModelCapability,
) -> None:
    """Register a provider-specific video capability override by model prefix."""
    if provider == "openai":
        from app.core.integrations.openai.video_capabilities import register_openai_video_capability

        register_openai_video_capability(model_prefix=model_prefix, capability=capability)
        return
    if provider == "volcengine":
        from app.core.integrations.volcengine.video_capabilities import register_volcengine_video_capability

        register_volcengine_video_capability(model_prefix=model_prefix, capability=capability)
        return
    if provider == "aliyun_bailian":
        from app.core.integrations.bailian.video_capabilities import register_bailian_video_capability

        register_bailian_video_capability(model_prefix=model_prefix, capability=capability)
        return
    if provider == "vidu":
        from app.core.integrations.vidu.video_capabilities import register_vidu_video_capability

        register_vidu_video_capability(model_prefix=model_prefix, capability=capability)
        return
    raise ValueError(f"Unsupported provider for video capability: {provider}")


def clear_video_model_capability_overrides(*, provider: ProviderKey | None = None) -> None:
    """Clear provider-specific video capability overrides for tests and resets."""
    from app.core.integrations.bailian.video_capabilities import clear_bailian_video_capability_overrides
    from app.core.integrations.openai.video_capabilities import clear_openai_video_capability_overrides
    from app.core.integrations.vidu.video_capabilities import clear_vidu_video_capability_overrides
    from app.core.integrations.volcengine.video_capabilities import clear_volcengine_video_capability_overrides

    clearers = {
        "openai": clear_openai_video_capability_overrides,
        "volcengine": clear_volcengine_video_capability_overrides,
        "aliyun_bailian": clear_bailian_video_capability_overrides,
        "vidu": clear_vidu_video_capability_overrides,
    }
    if provider is None:
        for clear in clearers.values():
            clear()
        return
    clearers[provider]()


def resolve_video_capability(*, provider: ProviderKey, model: str | None) -> VideoModelCapability:
    """Resolve provider/model video capability settings."""
    if provider == "openai":
        from app.core.integrations.openai.video_capabilities import resolve_openai_video_capability

        return resolve_openai_video_capability(model)
    if provider == "volcengine":
        from app.core.integrations.volcengine.video_capabilities import resolve_volcengine_video_capability

        return resolve_volcengine_video_capability(model)
    if provider == "aliyun_bailian":
        from app.core.integrations.bailian.video_capabilities import resolve_bailian_video_capability

        return resolve_bailian_video_capability(model)
    if provider == "vidu":
        from app.core.integrations.vidu.video_capabilities import resolve_vidu_video_capability

        return resolve_vidu_video_capability(model)
    raise ValueError(f"Unsupported provider for video capability: {provider}")


def infer_ratio_from_size(value: str | None) -> str | None:
    """Infer a supported ratio from a ratio string or WIDTHxHEIGHT size."""
    if not value:
        return None
    text = str(value).strip()
    if text in ALLOWED_RATIOS:
        return text
    if "x" not in text.lower():
        return None
    left, right = text.lower().split("x", 1)
    try:
        width = int(left.strip())
        height = int(right.strip())
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None

    ratio = width / height
    candidates = {
        "16:9": 16 / 9,
        "4:3": 4 / 3,
        "1:1": 1,
        "3:4": 3 / 4,
        "9:16": 9 / 16,
        "21:9": 21 / 9,
    }
    return min(candidates.items(), key=lambda item: abs(item[1] - ratio))[0]


def resolve_effective_ratio(input_: VideoGenerationInput) -> str | None:
    """Return the ratio already normalized by the business layer."""
    return input_.ratio


def resolve_default_ratio(*, provider: ProviderKey, model: str | None) -> str | None:
    """Return the provider/model default ratio."""
    cap = resolve_video_capability(provider=provider, model=model)
    if cap.default_ratio:
        return cap.default_ratio
    if cap.allowed_ratios:
        return sorted(cap.allowed_ratios)[0]
    return "16:9"


def derive_provider_size(
    *,
    provider: ProviderKey,
    model: str | None,
    ratio: VideoRatio,
) -> str | None:
    """Derive provider-specific size or resolution from a normalized ratio."""
    cap = resolve_video_capability(provider=provider, model=model)
    mapping = cap.ratio_to_size_mapping or DEFAULT_RATIO_TO_SIZE_MAPPING
    return mapping.get(ratio)


def validate_video_options(
    *,
    provider: ProviderKey,
    model: str | None,
    input_: VideoGenerationInput,
) -> None:
    """Validate shared input against provider/model video capabilities."""
    cap = resolve_video_capability(provider=provider, model=model)
    if input_.ratio and cap.allowed_ratios is not None and input_.ratio not in cap.allowed_ratios:
        raise ValueError(
            f"Unsupported ratio for provider={provider} model={model or '<default>'}: {input_.ratio}. "
            f"Allowed: {sorted(cap.allowed_ratios)}"
        )
    if input_.seconds is not None:
        if cap.min_seconds is not None and input_.seconds < cap.min_seconds:
            raise ValueError(f"seconds must be >= {cap.min_seconds}")
        if cap.max_seconds is not None and input_.seconds > cap.max_seconds:
            raise ValueError(f"seconds must be <= {cap.max_seconds}")
    if input_.seed is not None and not cap.supports_seed:
        raise ValueError(f"seed is not supported by provider={provider} model={model or '<default>'}")
    if input_.watermark is not None and not cap.supports_watermark:
        raise ValueError(f"watermark is not supported by provider={provider} model={model or '<default>'}")
