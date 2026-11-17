from __future__ import annotations

from typing import Protocol


class TTSProvider(Protocol):
    def synthesize(self, *, text: str, emotion: str = "", speaker: str = "") -> bytes:
        """Return wav/mp3 bytes."""


def get_tts_provider(engine: str = "edge", **kwargs):
    e = (engine or "edge").lower()
    if e == "edge":
        from app.services.tts.edge_provider import EdgeTTSProvider

        return EdgeTTSProvider(**kwargs)
    if e in ("voxcpm", "vox"):
        from app.services.tts.voxcpm_provider import VoxCPMProvider

        return VoxCPMProvider(**kwargs)
    raise ValueError(f"unknown tts engine: {engine}")
