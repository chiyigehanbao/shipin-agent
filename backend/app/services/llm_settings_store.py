from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) >= 4:
        return "***" + key[-4:]
    return "***"


def _default_profiles() -> list[dict[str, Any]]:
    return [
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "",
            "model": "deepseek-chat",
        }
    ]


class LlmSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read_file(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write_file(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _normalize(self, file_cfg: dict[str, Any]) -> dict[str, Any]:
        cfg = dict(file_cfg)
        profiles = cfg.get("cloud_profiles")
        if isinstance(profiles, list) and profiles:
            if not cfg.get("active_cloud_id"):
                cfg["active_cloud_id"] = profiles[0].get("id") or "legacy"
            return cfg

        has_legacy = any(
            cfg.get(k)
            for k in ("cloud_llm_base_url", "cloud_llm_api_key", "cloud_llm_model")
        )
        if has_legacy:
            cfg["cloud_profiles"] = [
                {
                    "id": "legacy",
                    "name": "Legacy",
                    "base_url": cfg.get("cloud_llm_base_url") or "",
                    "api_key": cfg.get("cloud_llm_api_key") or "",
                    "model": cfg.get("cloud_llm_model") or "",
                }
            ]
            cfg["active_cloud_id"] = "legacy"
            return cfg

        cfg["cloud_profiles"] = _default_profiles()
        cfg["active_cloud_id"] = "deepseek"
        return cfg

    def _active_profile(self, cfg: dict[str, Any]) -> dict[str, Any]:
        profiles = cfg.get("cloud_profiles") or []
        aid = cfg.get("active_cloud_id")
        for p in profiles:
            if p.get("id") == aid:
                return p
        return profiles[0] if profiles else {}

    def save(self, data: dict[str, Any]) -> None:
        current = self._normalize(self._read_file())
        for k in (
            "ollama_base_url",
            "ollama_model",
            "llm_timeout_sec",
            "active_cloud_id",
        ):
            if k in data and data[k] is not None:
                current[k] = data[k]

        if "cloud_profiles" in data and data["cloud_profiles"] is not None:
            old_by_id = {
                p.get("id"): p for p in (current.get("cloud_profiles") or []) if p.get("id")
            }
            new_profiles: list[dict[str, Any]] = []
            for p in data["cloud_profiles"]:
                pid = p.get("id") or ""
                old = old_by_id.get(pid) or {}
                key = p.get("api_key")
                if key is None or key == "":
                    key = old.get("api_key") or ""
                new_profiles.append(
                    {
                        "id": pid,
                        "name": p.get("name") or pid or "cloud",
                        "base_url": p.get("base_url") or "",
                        "api_key": key,
                        "model": p.get("model") or "",
                    }
                )
            current["cloud_profiles"] = new_profiles

        # keep flat cloud fields in sync for older readers
        active = self._active_profile(current)
        current["cloud_llm_base_url"] = active.get("base_url") or ""
        current["cloud_llm_api_key"] = active.get("api_key") or ""
        current["cloud_llm_model"] = active.get("model") or ""

        # legacy flat key update (single-field saves)
        if "cloud_llm_api_key" in data and data["cloud_llm_api_key"]:
            # if saving old-style key without profiles, push into active
            aid = current.get("active_cloud_id")
            for p in current.get("cloud_profiles") or []:
                if p.get("id") == aid:
                    p["api_key"] = data["cloud_llm_api_key"]
                    current["cloud_llm_api_key"] = data["cloud_llm_api_key"]
                    break
        for flat_k, profile_k in (
            ("cloud_llm_base_url", "base_url"),
            ("cloud_llm_model", "model"),
        ):
            if flat_k in data and data[flat_k] is not None and data[flat_k] != "":
                aid = current.get("active_cloud_id")
                for p in current.get("cloud_profiles") or []:
                    if p.get("id") == aid:
                        p[profile_k] = data[flat_k]
                        current[flat_k] = data[flat_k]
                        break

        self._write_file(current)

    def get_effective(self, **defaults: Any) -> dict[str, Any]:
        file_cfg = self._normalize(self._read_file())
        out = dict(defaults)
        for k in ("ollama_base_url", "ollama_model", "llm_timeout_sec"):
            v = file_cfg.get(k)
            if v is not None and v != "":
                out[k] = v
        active = self._active_profile(file_cfg)
        out["cloud_llm_base_url"] = active.get("base_url") or out.get("cloud_llm_base_url") or ""
        out["cloud_llm_api_key"] = active.get("api_key") or ""
        out["cloud_llm_model"] = active.get("model") or out.get("cloud_llm_model") or ""
        out["api_key_set"] = bool(out.get("cloud_llm_api_key"))
        out["active_cloud_id"] = file_cfg.get("active_cloud_id")
        return out

    def get_public(self, **defaults: Any) -> dict[str, Any]:
        file_cfg = self._normalize(self._read_file())
        eff = self.get_effective(**defaults)
        profiles_pub = []
        for p in file_cfg.get("cloud_profiles") or []:
            key = p.get("api_key") or ""
            profiles_pub.append(
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "base_url": p.get("base_url") or "",
                    "model": p.get("model") or "",
                    "api_key_set": bool(key),
                    "api_key_masked": _mask_key(key),
                }
            )
        key = eff.get("cloud_llm_api_key") or ""
        return {
            "ollama_base_url": eff["ollama_base_url"],
            "ollama_model": eff["ollama_model"],
            "llm_timeout_sec": eff.get("llm_timeout_sec") or 60.0,
            "active_cloud_id": file_cfg.get("active_cloud_id"),
            "cloud_profiles": profiles_pub,
            "cloud_llm_base_url": eff.get("cloud_llm_base_url") or "",
            "cloud_llm_model": eff.get("cloud_llm_model") or "",
            "api_key_set": bool(key),
            "cloud_llm_api_key_masked": _mask_key(key),
        }
