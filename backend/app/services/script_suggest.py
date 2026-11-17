# ============================================
# 剧本智能建议：基于场景数据的启发式 + LLM 增强
# ============================================
# 输出面向创作的结构化建议（问题 / 严重级 / 建议），供剧本工坊"智能建议栏"展示。
# LLM 不可用时降级为纯规则检测，仍返回可用建议，不抛错。
# ============================================

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.json_utils import parse_llm_json

DEFAULT_PACK = (
    Path(__file__).resolve().parent.parent
    / "prompt_packs"
    / "script_suggest_v1"
    / "system.md"
)

# 反派/配角常被一笔带过的信号词（中文台词上下文匹配用）
_VILLAIN_CUES = (
    "反派", "真凶", "凶手", "幕后", "boss", "Boss", "幕后黑手",
    "神秘人", "黑衣人", "对手", "仇家", "敌人", "恶人", "魔头",
)
_PLACEHOLDER_CUES = (
    "反派", "配角", "追兵", "路人", "小弟", "手下", "神秘人",
    "黑衣人", "陌生人", "某人", "对方",
)


def _scene_text(scene: dict[str, Any]) -> str:
    parts = [
        str(scene.get("name") or ""),
        str(scene.get("location") or ""),
        str(scene.get("description") or ""),
        str(scene.get("prompt_cn") or ""),
    ]
    for ln in scene.get("lines") or []:
        parts.append(str(ln.get("text") or ""))
    return "\n".join(parts)


def _has_cue_line(
    scene: dict[str, Any], cues: tuple[str, ...]
) -> bool:
    text = _scene_text(scene)
    return any(cue in text for cue in cues)


def _speakers(scene: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for ln in scene.get("lines") or []:
        speaker = str(ln.get("speaker") or "").strip()
        if speaker and speaker != "旁白":
            out.add(speaker)
    return out


def _rule_suggestions(scenes: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    total = len(scenes)
    if total == 0:
        return out

    # 1. 场景无对白
    silent = [s for s in scenes if not (s.get("lines") or [])]
    if silent:
        names = "、".join(
            str(s.get("name") or f"场景{idx + 1}") for idx, s in enumerate(scenes) if s in silent
        )[:60]
        out.append(
            {
                "issue": f"有 {len(silent)} 个场景没有对白（{names}）",
                "severity": "warning",
                "suggestion": "先为沉默场景补台词或行动目的，避免信息量断层拖慢节奏",
            }
        )

    # 2. 反派/关键对手角色只有标签、无姓名与背景
    villain_refs = [s for s in scenes if _has_cue_line(s, _VILLAIN_CUES)]
    if villain_refs:
        out.append(
            {
                "issue": "剧本出现过反派/对手类角色标签，但缺乏姓名与详细背景描写",
                "severity": "warning",
                "suggestion": "为反派补充动机、前史与欲望，冲突才立得住，观众才有代入感",
            }
        )

    # 4. 出场角色缺乏形貌/身份描写（场景描述过短）
    thin = [
        s
        for s in scenes
        if len((s.get("description") or "").strip()) < 40
        and len((s.get("prompt_cn") or "").strip()) < 40
        and (s.get("lines") or [])
    ]
    if thin:
        names = "、".join(
            str(s.get("name") or f"场景{idx + 1}") for idx, s in enumerate(scenes) if s in thin
        )[:60]
        out.append(
            {
                "issue": f"{len(thin)} 个场景的场面描写过短（{names}），画面信息量不足",
                "severity": "info",
                "suggestion": "补充环境、光线、动作细节，出图与剪辑才有表达依据",
            }
        )

    # 5. 有镜头感建议的通用提示（仅当以上都未触发）
    if total >= 3 and len(out) < 3:
        out.append(
            {
                "issue": "三幕节奏可再检查：开局钩子、中段升级、结尾反转是否都清晰",
                "severity": "info",
                "suggestion": "按强追逐/强决策拆结构，每场尾部留推进钩子",
            }
        )
    return out[:5]


class ScriptSuggestError(Exception):
    pass


class ScriptSuggestService:
    def __init__(
        self,
        llm: Any | None = None,
        *,
        pack_path: Path | None = None,
    ) -> None:
        self.llm = llm
        self.pack_path = pack_path or DEFAULT_PACK

    def suggest(self, scenes: list[dict[str, Any]]) -> list[dict[str, str]]:
        if not scenes:
            return []
        base = _rule_suggestions(scenes)
        if self.llm is None:
            return base
        try:
            llm_out = self._call_llm(scenes)
            if isinstance(llm_out, list) and llm_out:
                merged = list(llm_out) + base
                seen: set[str] = set()
                deduped: list[dict[str, str]] = []
                for item in merged:
                    issue = str(item.get("issue") or "").strip()
                    if issue and issue not in seen:
                        seen.add(issue)
                        deduped.append(
                            {
                                "issue": issue,
                                "severity": str(item.get("severity") or "info"),
                                "suggestion": str(item.get("suggestion") or "").strip(),
                            }
                        )
                return deduped[:6]
        except Exception:
            # LLM 失败不影响功能，返回规则结果
            pass
        return base

    def _call_llm(self, scenes: list[dict[str, Any]]) -> list[dict[str, str]]:
        system = self.pack_path.read_text(encoding="utf-8")
        payload = []
        for s in scenes:
            payload.append(
                {
                    "name": s.get("name"),
                    "location": s.get("location"),
                    "characters": s.get("characters") or [],
                    "description": s.get("description"),
                    "prompt_cn": s.get("prompt_cn"),
                    "lines": [
                        {
                            "type": ln.get("type"),
                            "speaker": ln.get("speaker"),
                            "text": ln.get("text"),
                        }
                        for ln in (s.get("lines") or [])
                    ],
                }
            )
        user = "scenes=\n" + json.dumps(payload, ensure_ascii=False)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        raw, _provider = self.llm.chat(messages)  # type: ignore[union-attr]
        return self._parse(raw)

    def _parse(self, raw: str) -> list[dict[str, str]]:
        data = parse_llm_json(raw)
        items = data.get("suggestions") or data.get("issues") or []
        if not isinstance(items, list):
            raise ScriptSuggestError("missing suggestions list")
        return [i for i in items if isinstance(i, dict)]