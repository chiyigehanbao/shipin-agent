"""Heuristic storyboard consistency checks (metadata, not vision)."""
from __future__ import annotations

from typing import Any


def _chars(value: Any) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    parts = []
    for chunk in text.replace("，", ",").replace("、", ",").replace("/", ",").split(","):
        name = chunk.strip()
        if name:
            parts.append(name)
    return set(parts)


def check_storyboard_consistency(frames: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return warnings/errors derived from frame metadata.

    Does not inspect pixels — that needs a vision model later.
    """
    ordered = sorted(frames or [], key=lambda f: int(f.get("number") or 0))
    issues: list[dict[str, str]] = []

    by_scene: dict[str, list[dict[str, Any]]] = {}
    for fr in ordered:
        sid = str(fr.get("scene_id") or fr.get("scene") or "").strip() or "__none__"
        by_scene.setdefault(sid, []).append(fr)

    for sid, group in by_scene.items():
        if sid == "__none__" or len(group) < 2:
            continue
        union: set[str] = set()
        for fr in group:
            union |= _chars(fr.get("character"))
        if len(union) <= 1:
            continue
        # Majority character set among frames that declare characters
        declared = [_chars(fr.get("character")) for fr in group if _chars(fr.get("character"))]
        if not declared:
            continue
        # Flag adjacent frames in this scene with conflicting non-empty casts
        for a, b in zip(group, group[1:]):
            ca, cb = _chars(a.get("character")), _chars(b.get("character"))
            if ca and cb and ca != cb:
                issues.append(
                    {
                        "frame_id": str(b.get("id") or ""),
                        "issue": (
                            f"第{b.get('number')}帧角色与第{a.get('number')}帧不一致"
                            f"（{','.join(sorted(ca))} → {','.join(sorted(cb))}）"
                        ),
                        "severity": "warning",
                        "suggestion": "统一该场景角色字段，或重新生成以保持出场一致",
                    }
                )

    for fr in ordered:
        desc = (fr.get("description") or "").strip()
        pe = (fr.get("prompt_en") or "").strip()
        de = (fr.get("description_en") or "").strip()
        if desc and not pe and not de and not fr.get("image_url"):
            issues.append(
                {
                    "frame_id": str(fr.get("id") or ""),
                    "issue": f"第{fr.get('number')}帧尚无英文提示词（出图将用镜头描述降级）",
                    "severity": "info",
                    "suggestion": "可先润色提示词再出图，提升英文控制力",
                }
            )

    # Deduplicate by (frame_id, issue)
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for item in issues:
        key = (item.get("frame_id") or "", item.get("issue") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
