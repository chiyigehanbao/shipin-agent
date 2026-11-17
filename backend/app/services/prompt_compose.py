from __future__ import annotations

import re
from typing import Any

# Pack instructions that models sometimes paste into lock_en / prompt_en.
_INSTRUCTION_LEAKS = (
    "not a poster climax",
    "plain or simple location",
    "standing or chest-up",
    "one reference still",
    "no markdown fences",
    "output json only",
    "lived-in film still",
    "cinematic masterpiece",
)


def collect_lock_ens(
    assets: list[dict[str, Any]],
    *,
    character_name: str = "",
    scene_name: str = "",
) -> list[str]:
    wanted: list[tuple[str, str]] = []
    if (character_name or "").strip():
        wanted.append(("character", character_name.strip()))
    if (scene_name or "").strip():
        wanted.append(("scene", scene_name.strip()))
    locks: list[str] = []
    for kind, name in wanted:
        for asset in assets:
            if asset.get("type") == kind and (asset.get("name") or "").strip() == name:
                lock = (asset.get("lock_en") or "").strip()
                if lock:
                    locks.append(lock)
                break
    return locks


def compose_still_prompt(shot_body: str, locks: list[str]) -> str:
    body = (shot_body or "").strip()
    parts: list[str] = []
    joined = ""
    for raw in locks or []:
        lock = (raw or "").strip()
        if not lock:
            continue
        if lock in body or lock in joined:
            continue
        parts.append(lock)
        joined = "\n\n".join(parts)
    if not parts:
        return body
    if not body:
        return "\n\n".join(parts)
    return "\n\n".join(parts + [body])


def _fallback_motion(frame: dict[str, Any]) -> str:
    action = (
        (frame.get("description_en") or "").strip()
        or (frame.get("description") or "").strip()
        or "The subject makes one small, complete action."
    )
    movement = (frame.get("movement") or "固定").strip() or "固定"
    duration = frame.get("duration")
    try:
        seconds = float(duration) if duration is not None else 5.0
    except (TypeError, ValueError):
        seconds = 5.0
    seconds = max(2.0, min(seconds, 8.0))
    return (
        f"{action} Camera: {movement}. About {seconds:.0f}s. "
        "Keep identity and wardrobe unchanged from the first frame."
    )


def resolve_i2v_prompt(frame: dict[str, Any]) -> str:
    motion = (frame.get("motion_prompt_en") or "").strip()
    if motion:
        return motion
    return _fallback_motion(frame)


def _strip_leaked_instructions(text: str) -> str:
    out = text or ""
    for phrase in _INSTRUCTION_LEAKS:
        out = re.sub(re.escape(phrase), "", out, flags=re.IGNORECASE)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*,+", ", ", out)
    return out.strip(" ,.;")


def sanitize_lock_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Drop leaked pack instructions from LLM lock/prompt fields."""
    cleaned = dict(data)
    for key in ("lock_en", "prompt_en", "prompt_cn", "motion_prompt_en"):
        if key in cleaned:
            cleaned[key] = _strip_leaked_instructions(str(cleaned.get(key) or ""))
    return cleaned


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_OPEN_PAREN = r"[(\uff08]"
_CLOSE_PAREN = r"[)\uff09]"


def _canonical_person_name(name: str, texts: list[str]) -> str:
    """Keep full pinyin if already present; otherwise the given name as-is."""
    if not _CJK_RE.search(name):
        return name
    full = re.compile(
        rf"\b([A-Za-z]{{2,12}})\s+([A-Za-z]{{2,12}})\s*"
        rf"{_OPEN_PAREN}\s*{re.escape(name)}\s*{_CLOSE_PAREN}"
    )
    for text in texts:
        match = full.search(text or "")
        if match:
            return f"{match.group(1).title()} {match.group(2).title()} ({name})"
    return name


def restore_given_name(data: dict[str, Any], name: str) -> dict[str, Any]:
    """Force lock/prompt fields to keep the given name; drop truncated nicknames."""
    name = (name or "").strip()
    if not name:
        return data
    cleaned = dict(data)
    keys = ("lock_en", "prompt_en", "prompt_cn")
    texts = [str(cleaned.get(key) or "") for key in keys]
    canon = _canonical_person_name(name, texts)
    nick = re.compile(
        rf"\b[A-Za-z]{{1,8}}\s+[A-Za-z]\s*"
        rf"{_OPEN_PAREN}\s*{re.escape(name)}\s*{_CLOSE_PAREN}"
    )
    for key in keys:
        text = str(cleaned.get(key) or "")
        label = name if key == "prompt_cn" else canon
        text = nick.sub(label, text)
        missing = name not in text
        if missing and not _CJK_RE.search(name):
            missing = name.lower() not in text.lower()
        if missing:
            text = f"{label}, {text}".strip(", ") if text else label
        cleaned[key] = text
    return cleaned


def character_portrait_split_error(lock_en: str, prompt_en: str) -> str:
    """Empty string if lock/prompt are a valid split; otherwise why they fail."""
    lock = (lock_en or "").strip()
    prompt = (prompt_en or "").strip()
    if not lock:
        return "missing lock_en"
    if prompt == lock:
        return "prompt_en must add staging, not copy lock_en"
    extra = prompt
    if prompt.lower().startswith(lock.lower()):
        extra = prompt[len(lock) :].strip()
    if len(extra) < 50:
        return "prompt_en staging too thin"
    return ""
