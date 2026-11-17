from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.services.llm_provider import LLMError
from app.services.llm_runtime import (
    build_llm_provider,
    effective_llm_kwargs,
    llm_store,
    public_llm_settings,
)

router = APIRouter()


class CloudProfileIn(BaseModel):
    id: str
    name: str = ""
    base_url: str = ""
    api_key: Optional[str] = None
    model: str = ""


class LlmSettingsUpdate(BaseModel):
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    cloud_llm_base_url: Optional[str] = None
    cloud_llm_api_key: Optional[str] = None
    cloud_llm_model: Optional[str] = None
    llm_timeout_sec: Optional[float] = None
    active_cloud_id: Optional[str] = None
    cloud_profiles: Optional[list[CloudProfileIn]] = None


@router.get("/paths")
async def get_paths():
    return {
        "modelhub_root": str(settings.modelhub_root),
        "outputs_dir": str(settings.media_mount_dir),
        "sqlite_path": str(settings.resolved_sqlite_path),
    }


@router.get("/llm")
async def get_llm_settings():
    pub = public_llm_settings()
    # 若配置的模型不在本机，自动对齐到已安装的第一项并写回
    try:
        kw = effective_llm_kwargs()
        base = (kw.get("ollama_base_url") or "").rstrip("/")
        if base:
            r = httpx.get(f"{base}/api/tags", timeout=5.0)
            r.raise_for_status()
            names = [
                m.get("name")
                for m in (r.json().get("models") or [])
                if m.get("name")
            ]
            pub["ollama_installed"] = names
            current = pub.get("ollama_model") or ""
            if names and current not in names:
                llm_store().save({"ollama_model": names[0]})
                pub = public_llm_settings()
                pub["ollama_installed"] = names
                pub["ollama_model_auto_fixed"] = True
                pub["ollama_model_was"] = current
    except Exception:
        pub.setdefault("ollama_installed", [])
    return pub


@router.put("/llm")
async def put_llm_settings(body: LlmSettingsUpdate):
    payload: dict[str, Any] = body.model_dump(exclude_unset=True)
    if "cloud_profiles" in payload and payload["cloud_profiles"] is not None:
        payload["cloud_profiles"] = [
            p if isinstance(p, dict) else p for p in payload["cloud_profiles"]
        ]
    llm_store().save(payload)
    return await get_llm_settings()


@router.post("/llm/test")
async def test_llm_settings():
    provider = build_llm_provider()
    try:
        text, name = provider.chat([{"role": "user", "content": "Reply with OK"}])
        return {"ok": True, "provider": name, "sample": text[:80]}
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/llm/ollama/models")
async def list_ollama_models():
    kw = effective_llm_kwargs()
    base = (kw.get("ollama_base_url") or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail="ollama_base_url 未配置")
    try:
        r = httpx.get(f"{base}/api/tags", timeout=5.0)
        r.raise_for_status()
        models = [
            {"name": m.get("name")}
            for m in (r.json().get("models") or [])
            if m.get("name")
        ]
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"无法连接 Ollama: {e}") from e
