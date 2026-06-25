"""Synchronous LLM runtime helpers used by Celery workers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.models.studio import Project
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
    model_id: str | None = None,
) -> tuple[Provider, Model]:
    """Resolve an owned model and its provider for synchronous worker code.

    Explicit ``model_id`` is used for project-level overrides. When it is empty,
    the helper preserves the existing behavior and reads the user's default model
    from ``model_settings``.
    """
    if model_id is None:
        settings_row = db.execute(select(ModelSettings).where(ModelSettings.user_id == user_id)).scalar_one_or_none()
        model_id = _default_model_id(settings_row, category)
    if not model_id:
        raise HTTPException(status_code=503, detail=f"No default model configured for category={category.value}")

    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=503, detail=f"Configured default model not found: {model_id}")
    if model.user_id != user_id or model.category != category:
        raise HTTPException(status_code=503, detail=f"Configured model is not usable for category={category.value}: {model_id}")

    provider = db.get(Provider, model.provider_id)
    if provider is None:
        raise HTTPException(status_code=503, detail=f"Provider not found for model_id={model.id}")

    return provider, model


def _project_text_model_id_sync(db: Session, *, user_id: str, project_id: str | None) -> str | None:
    """Return a project's selected text model id, or None to use user default."""
    normalized_project_id = (project_id or "").strip()
    if not normalized_project_id:
        return None
    project = db.get(Project, normalized_project_id)
    if project is None or project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.text_model_id


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


def build_project_text_llm_sync(
    db: Session,
    *,
    user_id: str,
    project_id: str | None,
    thinking: bool,
) -> BaseChatModel:
    """Build the project's selected text LLM, falling back to the user default."""
    provider, model = _require_provider_and_model_sync(
        db,
        user_id=user_id,
        category=ModelCategoryKey.text,
        model_id=_project_text_model_id_sync(db, user_id=user_id, project_id=project_id),
    )
    return _build_text_llm_from_model_sync(provider=provider, model=model, thinking=thinking)
