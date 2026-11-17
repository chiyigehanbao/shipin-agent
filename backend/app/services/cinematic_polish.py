# ============================================
# 电影感润色：按 stage 加载 pack + LLM + JSON 校验（缺字段重试一次）
# ============================================
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.llm_provider import LLMProvider

PACK_DIR = Path(__file__).resolve().parent.parent / "prompt_packs"
DEFAULT_PACK = PACK_DIR / "cinematic_v1" / "system.md"
PACK_VERSION = "cinematic-v1"

PACK_BY_STAGE: dict[str, tuple[Path, str]] = {
    "script_scene": (PACK_DIR / "cinematic_v1" / "system.md", "cinematic-v1"),
    "asset": (PACK_DIR / "cinematic_v1" / "system.md", "cinematic-v1"),
    "storyboard_frame": (PACK_DIR / "storyboard_still_v1" / "system.md", "storyboard-still-v1"),
    "character_lock": (PACK_DIR / "character_lock_v1" / "system.md", "character-lock-v1"),
    "scene_lock": (PACK_DIR / "scene_lock_v1" / "system.md", "scene-lock-v1"),
    "i2v_motion": (PACK_DIR / "i2v_motion_v1" / "system.md", "i2v-motion-v1"),
}


def _rag_type_for_stage(stage: str, ctx: dict[str, Any]) -> str | None:
    """Map polish stage to the RAG case type that best guides it."""
    if stage == "character_lock":
        return "character"
    if stage == "scene_lock":
        return "scene"
    if stage == "asset":
        kind = str(ctx.get("type") or "")
        return {"character": "character", "scene": "scene", "prop": "prop"}.get(kind)
    if stage == "storyboard_frame":
        return "storyboard"
    return "technique"


class PolishError(Exception):
    pass


def resolve_pack(stage: str, context: dict[str, Any] | None = None) -> tuple[Path, str]:
    ctx = context or {}
    if stage == "asset":
        kind = str(ctx.get("type") or "")
        if kind == "character":
            return PACK_BY_STAGE["character_lock"]
        if kind == "scene":
            return PACK_BY_STAGE["scene_lock"]
    return PACK_BY_STAGE.get(stage, PACK_BY_STAGE["script_scene"])


class CinematicPolishService:
    def __init__(self, llm: LLMProvider, *, pack_path: Path | None = None) -> None:
        self.pack_path = pack_path
        self.llm = llm

    def polish(
        self,
        *,
        stage: str,
        text_cn: str,
        text_en: str = "",
        context: dict[str, Any] | None = None,
        return_interpretation: bool = True,
    ) -> dict[str, Any]:
        ctx = context or {}
        pack_path, pack_version = resolve_pack(stage, ctx)
        if self.pack_path is not None:
            pack_path = self.pack_path
            pack_version = PACK_VERSION
        system = pack_path.read_text(encoding="utf-8")
        user = self._user_message(stage, text_cn, text_en, ctx, return_interpretation)
        try:
            from app.services.rag_retrieve import build_rag_context

            rag_type = _rag_type_for_stage(stage, ctx)
            rag_block = build_rag_context(
                f"{text_cn}\n{text_en}".strip(), top_k=3, type_filter=rag_type
            )
            if rag_block:
                user = f"{user}\n\n{rag_block}"
        except Exception:
            pass
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_err: Exception | None = None
        retry_hint = (
            "Return ONLY valid JSON with non-empty motion_prompt_en."
            if stage == "i2v_motion"
            else (
                "Return ONLY valid JSON. lock_en is appearance only with "
                "face geometry, hair, fabric wear, one object. "
                "prompt_en must copy lock_en then add staging: shot size, "
                "motivated light, materials, 50mm/85mm capture. "
                "Natural language for Flux, no weights, no 8K/masterpiece. "
                "They must not be the same string. Include avoid."
                if stage in {"character_lock", "scene_lock"}
                else "Return ONLY valid JSON with non-empty prompt_en and avoid."
            )
        )
        for _ in range(2):
            raw, provider = self.llm.chat(messages)
            try:
                data = self._parse_json(raw)
                self._validate(data, stage=stage)
                if not return_interpretation:
                    data["interpretation_cn"] = data.get("interpretation_cn") or ""
                data["provider"] = provider
                data["pack_version"] = pack_version
                data.setdefault("prompt_cn", "")
                data.setdefault("prompt_en", "")
                data.setdefault("avoid", "")
                data.setdefault("lock_en", "")
                data.setdefault("motion_prompt_en", "")
                from app.services.prompt_compose import restore_given_name, sanitize_lock_fields

                data = sanitize_lock_fields(data)
                name = str(ctx.get("asset_name") or ctx.get("name") or "").strip()
                if name:
                    data = restore_given_name(data, name)
                return data
            except (PolishError, json.JSONDecodeError, KeyError, TypeError) as e:
                last_err = e
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": retry_hint})
        raise PolishError(f"invalid polish output: {last_err}")

    def _user_message(
        self,
        stage: str,
        text_cn: str,
        text_en: str,
        context: dict[str, Any],
        return_interpretation: bool,
    ) -> str:
        lock = str(context.get("lock_en") or "").strip()
        text_en_s = (text_en or "").strip()
        name = str(context.get("asset_name") or context.get("name") or "").strip()
        notes = []
        if name:
            notes.append(
                f"Keep the character/place name exactly as '{name}'. "
                "Do not nickname or truncate it."
            )
        collapsed = bool(lock and text_en_s and lock == text_en_s)
        if lock and not collapsed:
            notes.append(
                "Copy lock_en VERBATIM into lock_en and the start of prompt_en. Do not paraphrase."
            )
        elif collapsed:
            notes.append(
                "Existing lock_en is identical to the English prompt; it is a draft. "
                "Rewrite a proper appearance-only lock_en and a longer prompt_en with staging."
            )
        if stage in {"character_lock", "scene_lock", "asset"}:
            notes.append(
                "text_cn may include a scene beat; extract identity/atmosphere. "
                "Do not paste pack instructions into the JSON fields."
            )
        note_block = ("\n" + "\n".join(notes) + "\n") if notes else ""
        return (
            f"stage={stage}\n"
            f"return_interpretation={return_interpretation}\n"
            f"text_cn={text_cn}\n"
            f"text_en={text_en}\n"
            f"{note_block}"
            f"context={json.dumps(context, ensure_ascii=False)}"
        )

    def _parse_json(self, raw: str) -> dict[str, Any]:
        from app.services.json_utils import parse_llm_json

        return parse_llm_json(raw)

    def _validate(self, data: dict[str, Any], *, stage: str) -> None:
        if stage == "i2v_motion":
            if not str(data.get("motion_prompt_en") or "").strip():
                raise PolishError("missing motion_prompt_en")
            return
        if not str(data.get("prompt_en") or "").strip():
            raise PolishError("missing prompt_en")
        if not str(data.get("avoid") or "").strip():
            raise PolishError("missing avoid")
        if stage in {"character_lock", "scene_lock"}:
            from app.services.prompt_compose import character_portrait_split_error

            err = character_portrait_split_error(
                str(data.get("lock_en") or ""),
                str(data.get("prompt_en") or ""),
            )
            if err:
                raise PolishError(err)
            if stage == "character_lock":
                from app.services.asset_readiness import lock_has_face_cue

                if not lock_has_face_cue(str(data.get("lock_en") or "")):
                    raise PolishError(
                        "lock_en must include a face cue (eyes/iris/gaze/jaw/face)"
                    )
