from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.services.llm_settings_store import LlmSettingsStore

STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "llm_settings.json"


def llm_store() -> LlmSettingsStore:
    return LlmSettingsStore(STORE_PATH)


def effective_llm_kwargs() -> dict[str, Any]:
    store = llm_store()
    return store.get_effective(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        cloud_llm_base_url=settings.cloud_llm_base_url,
        cloud_llm_api_key=settings.cloud_llm_api_key,
        cloud_llm_model=settings.cloud_llm_model,
        llm_timeout_sec=settings.llm_timeout_sec,
    )


def public_llm_settings() -> dict[str, Any]:
    return llm_store().get_public(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        cloud_llm_base_url=settings.cloud_llm_base_url,
        cloud_llm_api_key=settings.cloud_llm_api_key,
        cloud_llm_model=settings.cloud_llm_model,
        llm_timeout_sec=settings.llm_timeout_sec,
    )


def build_llm_provider():
    from app.services.llm_provider import LLMProvider

    kw = effective_llm_kwargs()
    return LLMProvider(
        ollama_base_url=kw["ollama_base_url"],
        ollama_model=kw["ollama_model"],
        cloud_llm_base_url=kw.get("cloud_llm_base_url") or "",
        cloud_llm_api_key=kw.get("cloud_llm_api_key") or "",
        cloud_llm_model=kw.get("cloud_llm_model") or "",
        timeout_sec=float(kw.get("llm_timeout_sec") or 60),
    )
