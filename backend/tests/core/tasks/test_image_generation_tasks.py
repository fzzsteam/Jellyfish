from __future__ import annotations

from app.core.contracts.image_generation import ImageGenerationInput
from app.core.contracts.provider import ProviderConfig
from app.core.tasks.image_generation_tasks import ImageGenerationTask


def test_vidu_image_generation_task_uses_long_default_timeout() -> None:
    """The provider-specific Vidu default should not be overwritten by the outer task default."""
    task = ImageGenerationTask(
        provider_config=ProviderConfig(provider="vidu", api_key="vidu-key"),
        input_=ImageGenerationInput(prompt="asset", model="viduq2"),
    )

    assert task._impl._timeout_s == 300.0


def test_vidu_image_generation_task_allows_explicit_timeout_override() -> None:
    """Explicit task timeouts remain respected for tests or specialized callers."""
    task = ImageGenerationTask(
        provider_config=ProviderConfig(provider="vidu", api_key="vidu-key"),
        input_=ImageGenerationInput(prompt="asset", model="viduq2"),
        timeout_s=42.0,
    )

    assert task._impl._timeout_s == 42.0
