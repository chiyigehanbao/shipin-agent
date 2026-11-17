# Normalize / count structured dialogue & narration lines
from __future__ import annotations

import uuid
from typing import Any


def normalize_lines(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        typ = str(item.get("type") or "dialogue").strip().lower()
        if typ not in ("dialogue", "narration"):
            typ = "dialogue"
        lid = str(item.get("id") or "").strip() or f"line_{uuid.uuid4().hex[:8]}"
        speaker = str(item.get("speaker") or "").strip()
        if typ == "narration" and not speaker:
            speaker = "旁白"
        out.append(
            {
                "id": lid,
                "type": typ,
                "speaker": speaker,
                "text": text,
                "emotion": str(item.get("emotion") or "").strip(),
            }
        )
    return out


def counts_from_lines(lines: list[dict[str, Any]]) -> tuple[int, int]:
    d = sum(1 for x in lines if x.get("type") == "dialogue")
    n = sum(1 for x in lines if x.get("type") == "narration")
    return d, n
