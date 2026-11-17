from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ComfySettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_base_url(self) -> str | None:
        url = (self._read().get("base_url") or "").strip()
        return url or None

    def save_base_url(self, url: str) -> str:
        url = url.rstrip("/")
        data = self._read()
        data["base_url"] = url
        self._write(data)
        return url


def default_comfy_settings_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "comfyui_settings.json"
