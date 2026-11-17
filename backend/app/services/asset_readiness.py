# Character readiness for storyboard quality gates.
from __future__ import annotations

from typing import Any


_FACE_CUES = ("eye", "eyes", "iris", "gaze", "jaw", "cheek", "face", "brow", "lid")


def is_character_ready(asset: dict[str, Any] | None) -> bool:
    if not asset or asset.get("type") != "character":
        return False
    if str(asset.get("selection_status") or "legacy") in {"candidate", "rejected"}:
        return False
    lock = str(asset.get("lock_en") or "").strip()
    image = str(asset.get("image_url") or "").strip()
    return bool(lock and image and asset.get("status") == "completed")


def readiness_reasons(asset: dict[str, Any] | None) -> list[str]:
    if not asset or asset.get("type") != "character":
        return ["not_character"]
    reasons: list[str] = []
    if str(asset.get("selection_status") or "legacy") in {"candidate", "rejected"}:
        reasons.append("not_selected")
    if not str(asset.get("lock_en") or "").strip():
        reasons.append("empty_lock")
    if not str(asset.get("image_url") or "").strip():
        reasons.append("missing_image")
    if asset.get("status") != "completed":
        reasons.append("not_completed")
    return reasons


def lock_has_face_cue(lock_en: str) -> bool:
    low = (lock_en or "").lower()
    return any(cue in low for cue in _FACE_CUES)


def unready_character_names(
    assets: list[dict[str, Any]],
    cast_names: list[str],
) -> list[str]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        name = str(asset.get("name") or "").strip()
        if asset.get("type") == "character" and name:
            by_name.setdefault(name, []).append(asset)
    out: list[str] = []
    seen: set[str] = set()
    for raw in cast_names:
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if not any(is_character_ready(asset) for asset in by_name.get(name, [])):
            out.append(name)
    return out


def character_readiness_report(assets: list[dict[str, Any]]) -> dict[str, Any]:
    chars = [a for a in assets if a.get("type") == "character"]
    rows = []
    ready_count = 0
    for a in chars:
        ready = is_character_ready(a)
        if ready:
            ready_count += 1
        rows.append(
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "ready": ready,
                "reasons": [] if ready else readiness_reasons(a),
            }
        )
    return {
        "characters": rows,
        "ready_count": ready_count,
        "total_characters": len(chars),
    }
