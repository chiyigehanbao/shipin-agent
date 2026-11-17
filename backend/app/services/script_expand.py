# Script expand: load pack + LLM + JSON scenes validation (retry once)
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.services.llm_provider import LLMProvider
from app.services.script_lines import counts_from_lines, normalize_lines

PACK_VERSION = "script-expand-v1"
DEFAULT_PACK = (
    Path(__file__).resolve().parent.parent / "prompt_packs" / "script_expand_v1" / "system.md"
)


class ScriptExpandError(Exception):
    pass


class ScriptExpandService:
    def __init__(self, llm: LLMProvider, *, pack_path: Path | None = None) -> None:
        self.pack_path = pack_path or DEFAULT_PACK
        self.llm = llm

    def expand(self, *, text: str, style: str = "", mode: str = "expand") -> list[dict[str, Any]]:
        system = self.pack_path.read_text(encoding="utf-8")
        user = (
            f"mode={mode}\n"
            f"style={style or '短剧清晰脸、实拍感'}\n"
            f"硬性要求：\n"
            f"- 只输出 JSON {{\"scenes\":[...]}}；\n"
            f"- expand：通常 4–7 场；第一场要有钩子；每场有情节/关系/信息增量；\n"
            f"- 每场 lines 非空（expand≥3 且 dialogue≥2）；对白短狠可配音；\n"
            f"- description 写可见动作与调度，禁止五官发型服装长描述；\n"
            f"- 角色名全程冻结，与 speaker 一致。\n"
            f"text=\n{text}"
        )
        try:
            from app.services.rag_retrieve import build_rag_context

            rag_block = build_rag_context(f"{style}\n{text}", top_k=3)
            if rag_block:
                user = f"{user}\n\n{rag_block}"
        except Exception:
            pass
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_err: Exception | None = None
        for _ in range(3):
            raw, _provider = self.llm.chat(messages)
            try:
                data = self._parse_json(raw)
                scenes = self._normalize_scenes(data, mode=mode)
                if not scenes:
                    raise ScriptExpandError("empty scenes")
                return scenes
            except (ScriptExpandError, json.JSONDecodeError, KeyError, TypeError) as e:
                last_err = e
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f'输出无效：{e}. 请只返回 JSON：'
                            '{"scenes":[{...,"lines":[{type,speaker,text,emotion},...]}]}。'
                            "每个 scene 的 lines 必须非空；expand 模式每场至少 3 条（含不少于 2 条 dialogue），"
                            "必须覆盖足够多的台词让每个分镜帧都有话可说。"
                        ),
                    }
                )
        raise ScriptExpandError(f"invalid expand output: {last_err}")

    def _parse_json(self, raw: str) -> dict[str, Any]:
        from app.services.json_utils import parse_llm_json

        return parse_llm_json(raw)

    def _normalize_scenes(
        self, data: dict[str, Any], *, mode: str = "expand"
    ) -> list[dict[str, Any]]:
        scenes = data.get("scenes")
        if not isinstance(scenes, list):
            raise ScriptExpandError("scenes must be list")
        out: list[dict[str, Any]] = []
        min_lines = 3 if mode == "expand" else 2
        min_dialogue = 2 if mode == "expand" else 1
        for i, s in enumerate(scenes, start=1):
            if not isinstance(s, dict):
                continue
            lines = normalize_lines(s.get("lines"))
            d_count, n_count = counts_from_lines(lines)
            if len(lines) < min_lines:
                raise ScriptExpandError(
                    f"scene {i} needs >= {min_lines} lines, got {len(lines)}"
                )
            if d_count < min_dialogue:
                raise ScriptExpandError(
                    f"scene {i} needs >= {min_dialogue} dialogue, got {d_count}"
                )
            out.append(
                {
                    "number": int(s.get("number") or i),
                    "name": str(s.get("name") or f"场景{i}"),
                    "location": str(s.get("location") or ""),
                    "time": str(s.get("time") or ""),
                    "characters": list(s.get("characters") or []),
                    "props": list(s.get("props") or []),
                    "description": str(s.get("description") or ""),
                    "description_en": str(s.get("description_en") or ""),
                    "lines": lines,
                    "dialogue_count": d_count,
                    "narration_count": n_count,
                }
            )
        return out
