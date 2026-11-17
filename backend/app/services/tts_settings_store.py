from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TtsSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self) -> dict[str, Any]:
        cfg = self._read()
        return {
            "engine": cfg.get("engine") or "edge",
            "edge_voice": cfg.get("edge_voice") or "zh-CN-XiaoxiaoNeural",
        }

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        cur = self.get()
        if "engine" in data and data["engine"]:
            cur["engine"] = str(data["engine"])
        if "edge_voice" in data and data["edge_voice"]:
            cur["edge_voice"] = str(data["edge_voice"])
        self._write(cur)
        return cur


def default_tts_settings_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "tts_settings.json"
