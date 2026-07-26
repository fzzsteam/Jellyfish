"""Synchronous LLM runtime helpers used by Celery workers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.services.llm.provider_resolver import resolve_effective_base_url


def _default_model_id(settings_row: ModelSettings | None, category: ModelCategoryKey) -> str | None:
    """Return the user's configured default model id for a model category."""
    if settings_row is None:
        return None
    if category == ModelCategoryKey.text:
        return settings_row.default_text_model_id
    if category == ModelCategoryKey.image:
        return settings_row.default_image_model_id
    return settings_row.default_video_model_id


def _require_provider_and_model_sync(
    db: Session,
    *,
    user_id: str,
    category: ModelCategoryKey,
) -> tuple[Provider, Model]:
    """Resolve a user's default model and provider for synchronous worker code."""
    settings_row = db.execute(select(ModelSettings).where(ModelSettings.user_id == user_id)).scalar_one_or_none()
    model_id = _default_model_id(settings_row, category)
    if not model_id:
        raise HTTPException(status_code=503, detail=f"No default model configured for category={category.value}")

    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=503, detail=f"Configured default model not found: {model_id}")
    if model.category != category:
        raise HTTPException(status_code=503, detail=f"Configured model is not usable for category={category.value}: {model_id}")

    provider = db.get(Provider, model.provider_id)
    if provider is None:
        raise HTTPException(status_code=503, detail=f"Provider not found for model_id={model.id}")

    return provider, model


def _build_text_llm_from_model_sync(
    *,
    provider: Provider,
    model: Model,
    thinking: bool,
) -> BaseChatModel:
    """Build a LangChain ChatOpenAI instance from persisted provider/model rows."""
    api_key = (provider.api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail=f"Provider api_key is empty for provider_id={provider.id}")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise HTTPException(status_code=503, detail="Install langchain-openai to enable script-processing tasks") from e

    kwargs: dict[str, Any] = dict(model.params or {})
    kwargs["model"] = model.name
    kwargs["api_key"] = api_key
    kwargs.setdefault("temperature", 0)
    # 显式兜底请求超时：ChatOpenAI 默认 timeout=None 会让 openai SDK 关闭内置的
    # 600s 默认超时，供应商卡住时请求可无限期挂起（见 config.py 中的说明）。
    kwargs.setdefault("timeout", settings.llm_request_timeout_seconds)

    base_url = resolve_effective_base_url(provider=provider, category=ModelCategoryKey.text)
    if base_url:
        kwargs.setdefault("base_url", base_url)

    if not thinking:
        extra_body = dict(kwargs.get("extra_body") or {})
        extra_body["enable_thinking"] = False
        kwargs["extra_body"] = extra_body

    return ChatOpenAI(**kwargs)


def build_default_text_llm_sync(
    db: Session,
    *,
    user_id: str,
    thinking: bool,
) -> BaseChatModel:
    """Build the user's default text LLM for legacy worker callers."""
    provider, model = _require_provider_and_model_sync(db, user_id=user_id, category=ModelCategoryKey.text)
    return _build_text_llm_from_model_sync(provider=provider, model=model, thinking=thinking)
