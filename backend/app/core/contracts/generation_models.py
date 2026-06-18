from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.contracts.provider import ProviderKey

GenerationModelCategory = Literal["image", "video"]


@dataclass(frozen=True, slots=True)
class BuiltinGenerationModel:
    """System-owned generation model exposed in product UI without DB model CRUD."""

    id: str
    provider: ProviderKey
    category: GenerationModelCategory
    name: str
    display_name: str
    description: str = ""
    recommended: bool = False


BUILTIN_GENERATION_MODELS: tuple[BuiltinGenerationModel, ...] = (
    BuiltinGenerationModel(
        id="builtin:aliyun_bailian:image:qwen-image-2.0-pro",
        provider="aliyun_bailian",
        category="image",
        name="qwen-image-2.0-pro",
        display_name="qwen-image-2.0-pro",
        description="Aliyun Bailian high-quality image generation.",
    ),
    BuiltinGenerationModel(
        id="builtin:aliyun_bailian:image:wan2.7-image-pro",
        provider="aliyun_bailian",
        category="image",
        name="wan2.7-image-pro",
        display_name="wan2.7-image-pro",
        description="Aliyun Bailian WAN image generation.",
    ),
    BuiltinGenerationModel(
        id="builtin:aliyun_bailian:video:happyhorse-1.0-t2v",
        provider="aliyun_bailian",
        category="video",
        name="happyhorse-1.0-t2v",
        display_name="happyhorse-1.0-t2v",
        description="Aliyun Bailian text-to-video generation.",
        recommended=True,
    ),
    BuiltinGenerationModel(
        id="builtin:aliyun_bailian:video:happyhorse-1.0-i2v",
        provider="aliyun_bailian",
        category="video",
        name="happyhorse-1.0-i2v",
        display_name="happyhorse-1.0-i2v",
        description="Aliyun Bailian image-to-video generation.",
    ),
    BuiltinGenerationModel(
        id="builtin:aliyun_bailian:video:happyhorse-1.0-r2v",
        provider="aliyun_bailian",
        category="video",
        name="happyhorse-1.0-r2v",
        display_name="happyhorse-1.0-r2v",
        description="Aliyun Bailian reference-to-video generation.",
    ),
)


def list_builtin_generation_models(category: GenerationModelCategory | None = None) -> list[BuiltinGenerationModel]:
    """Return built-in generation models, optionally limited to one product category."""
    if category is None:
        return list(BUILTIN_GENERATION_MODELS)
    return [item for item in BUILTIN_GENERATION_MODELS if item.category == category]


def get_builtin_generation_model(model_id: str | None) -> BuiltinGenerationModel | None:
    """Resolve a built-in model id and return None for legacy DB model ids."""
    normalized = (model_id or "").strip()
    if not normalized.startswith("builtin:"):
        return None
    return next((item for item in BUILTIN_GENERATION_MODELS if item.id == normalized), None)


def get_recommended_builtin_generation_model(category: GenerationModelCategory) -> BuiltinGenerationModel:
    """Return the product default model for a category when no user selection is provided."""
    items = list_builtin_generation_models(category)
    for item in items:
        if item.recommended:
            return item
    return items[0]
