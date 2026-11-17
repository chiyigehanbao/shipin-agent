# ============================================
# TTS settings / preview / test
# ============================================
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.services.tts import get_tts_provider
from app.services.tts.voxcpm_provider import VoxCPMNotReady
from app.services.tts_settings_store import TtsSettingsStore, default_tts_settings_path

router = APIRouter()
_store = TtsSettingsStore(default_tts_settings_path())


class TtsSettingsBody(BaseModel):
    engine: Optional[str] = None
    edge_voice: Optional[str] = None


class TtsPreviewBody(BaseModel):
    text: str
    emotion: str = ""
    engine: Optional[str] = None


class TtsTestBody(BaseModel):
    engine: str = "edge"


@router.get("/settings")
def get_settings():
    return _store.get()


@router.put("/settings")
def put_settings(body: TtsSettingsBody):
    return _store.save(body.model_dump(exclude_unset=True))


@router.post("/preview")
def preview(body: TtsPreviewBody):
    cfg = _store.get()
    engine = body.engine or cfg["engine"]
    try:
        provider = get_tts_provider(engine, voice=cfg.get("edge_voice"))
        audio = provider.synthesize(text=body.text, emotion=body.emotion or "")
    except VoxCPMNotReady as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    out_dir = settings.media_mount_dir / "tts_preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"preview_{uuid.uuid4().hex[:10]}.mp3"
    path = out_dir / name
    path.write_bytes(audio)
    return {"audio_url": f"/media/tts_preview/{name}", "engine": engine}


@router.post("/test")
def test_engine(body: TtsTestBody):
    cfg = _store.get()
    engine = body.engine or cfg["engine"]
    try:
        provider = get_tts_provider(engine, voice=cfg.get("edge_voice"))
        audio = provider.synthesize(text="测试配音", emotion="")
    except VoxCPMNotReady as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True, "engine": engine, "bytes": len(audio)}
