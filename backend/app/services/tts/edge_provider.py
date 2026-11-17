from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path


async def _edge_save(text: str, path: str, voice: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


class EdgeTTSProvider:
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural", **_kwargs) -> None:
        self.voice = voice or "zh-CN-XiaoxiaoNeural"

    def synthesize(self, *, text: str, emotion: str = "", speaker: str = "") -> bytes:
        del emotion, speaker  # Edge: emotion optional / ignored
        text = (text or "").strip()
        if not text:
            raise ValueError("empty tts text")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            path = tmp.name
        try:
            asyncio.run(_edge_save(text, path, self.voice))
            return Path(path).read_bytes()
        finally:
            Path(path).unlink(missing_ok=True)
