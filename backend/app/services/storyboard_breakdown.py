# LLM storyboard breakdown: create frames and assign scene lines
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from app.db.repositories.frames import FrameRepository
from app.db.repositories.scenes import SceneRepository
from app.services.llm_provider import LLMProvider
from app.services.prompt_compose import (
    collect_lock_ens,
    compose_still_prompt,
    resolve_i2v_prompt,
)
from app.services.script_lines import normalize_lines

DEFAULT_PACK = (
    Path(__file__).resolve().parent.parent
    / "prompt_packs"
    / "storyboard_breakdown_v1"
    / "system.md"
)


class StoryboardBreakdownError(Exception):
    pass


class StoryboardBreakdownService:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        scene_repo: SceneRepository | None = None,
        frame_repo: FrameRepository | None = None,
        asset_repo: Any | None = None,
        pack_path: Path | None = None,
    ) -> None:
        self.llm = llm
        self.scene_repo = scene_repo or SceneRepository()
        self.frame_repo = frame_repo or FrameRepository()
        self.asset_repo = asset_repo
        self.pack_path = pack_path or DEFAULT_PACK

    def run(
        self,
        *,
        project_id: str,
        mode: str = "replace_empty",
        scene_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        scenes = self.scene_repo.list_by_project(project_id)
        if scene_ids:
            want = set(scene_ids)
            scenes = [s for s in scenes if s["id"] in want]
        if not scenes:
            return {"frame_count": 0, "created": 0}

        assets = self._list_assets(project_id)
        existing = self.frame_repo.list(project_id)
        if mode == "replace_empty":
            scenes = [
                s
                for s in scenes
                if not any(f.get("scene_id") == s["id"] for f in existing)
            ]
            if not scenes and existing:
                return {"frame_count": len(existing), "created": 0}
        elif mode == "rebuild_scene":
            for s in scenes:
                self.frame_repo.delete_by_scene(
                    project_id, s["id"], only_without_image=True
                )
        elif mode == "rebuild_all":
            for s in scenes:
                self.frame_repo.delete_by_scene(project_id, s["id"])
        elif mode == "assign_lines_only":
            return self._assign_lines_only(project_id, scenes)
        elif mode != "replace_empty":
            raise StoryboardBreakdownError(f"unknown mode: {mode}")

        if not scenes:
            return {"frame_count": len(self.frame_repo.list(project_id)), "created": 0}

        self._assert_characters_ready(project_id, scenes)

        planned = self._call_llm(scenes, assets)
        created = self._apply_plan(
            project_id, scenes, planned, assets, replace_existing=False
        )
        return {
            "frame_count": len(self.frame_repo.list(project_id)),
            "created": created,
        }

    def _assert_characters_ready(
        self, project_id: str, scenes: list[dict[str, Any]]
    ) -> None:
        from app.services.asset_readiness import unready_character_names

        assets = self._list_assets(project_id)
        cast: list[str] = []
        for s in scenes:
            for name in s.get("characters") or []:
                cast.append(str(name))
        unready = unready_character_names(assets, cast)
        if unready:
            joined = "、".join(unready)
            raise StoryboardBreakdownError(
                f"characters_not_ready: {joined} — 请先在资产生成完成定妆图与身份锁"
            )

    def _assign_lines_only(
        self, project_id: str, scenes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        planned = self._call_llm(scenes, self._list_assets(project_id))
        by_scene_lines = {s["id"]: {ln["id"]: ln for ln in s.get("lines") or []} for s in scenes}
        frames = self.frame_repo.list(project_id)
        # Clear lines on matching scenes then assign by order within scene
        for s in scenes:
            scene_frames = [f for f in frames if f.get("scene_id") == s["id"]]
            scene_frames.sort(key=lambda x: x.get("number") or 0)
            plan_frames = [p for p in planned if p.get("scene_id") == s["id"]]
            line_map = by_scene_lines.get(s["id"]) or {}
            used: set[str] = set()
            for i, fr in enumerate(scene_frames):
                ids = []
                if i < len(plan_frames):
                    ids = list(plan_frames[i].get("line_ids") or [])
                lines = []
                for lid in ids:
                    if lid in line_map and lid not in used:
                        lines.append(line_map[lid])
                        used.add(lid)
                self.frame_repo.update(project_id, fr["id"], lines=lines)
            leftover = [line_map[i] for i in line_map if i not in used]
            if leftover:
                if scene_frames:
                    last = scene_frames[-1]
                    merged = list(last.get("lines") or []) + leftover
                    self.frame_repo.update(project_id, last["id"], lines=merged)
                else:
                    desc = s.get("description") or s.get("name") or "镜头"
                    self.frame_repo.create(
                        project_id,
                        scene_id=s["id"],
                        scene=s.get("name") or "",
                        description=desc,
                        description_en=desc,
                        prompt_cn=desc,
                        prompt_en=desc,
                        lines=leftover,
                    )
        return {"frame_count": len(self.frame_repo.list(project_id)), "created": 0}

    def _list_assets(self, project_id: str) -> list[dict[str, Any]]:
        if self.asset_repo is not None:
            return self.asset_repo.list(project_id)
        try:
            from app.db.repositories.assets import AssetRepository

            return AssetRepository(self.frame_repo.db_path).list(project_id)
        except Exception:
            return []

    def _locks_for_scene(
        self, scene: dict[str, Any], assets: list[dict[str, Any]]
    ) -> list[str]:
        locks: list[str] = []
        seen: set[str] = set()
        for raw in scene.get("characters") or []:
            for lock in collect_lock_ens(
                assets, character_name=str(raw), scene_name=""
            ):
                if lock not in seen:
                    seen.add(lock)
                    locks.append(lock)
        loc = (scene.get("location") or scene.get("name") or "").strip()
        for lock in collect_lock_ens(assets, character_name="", scene_name=loc):
            if lock not in seen:
                seen.add(lock)
                locks.append(lock)
        return locks

    def _call_llm(
        self, scenes: list[dict[str, Any]], assets: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        system = self.pack_path.read_text(encoding="utf-8")
        payload = []
        for s in scenes:
            locks = self._locks_for_scene(s, assets)
            payload.append(
                {
                    "id": s["id"],
                    "name": s.get("name"),
                    "location": s.get("location"),
                    "time": s.get("time"),
                    "characters": s.get("characters") or [],
                    "description": s.get("description"),
                    "character_locks": locks,
                    "scene_lock": next(
                        (
                            lock
                            for lock in collect_lock_ens(
                                assets,
                                character_name="",
                                scene_name=(s.get("location") or s.get("name") or ""),
                            )
                        ),
                        "",
                    ),
                    "lines": [
                        {
                            "id": ln["id"],
                            "type": ln["type"],
                            "speaker": ln.get("speaker"),
                            "text": ln.get("text"),
                        }
                        for ln in (s.get("lines") or [])
                    ],
                }
            )
        user = "scenes=\n" + json.dumps(payload, ensure_ascii=False)
        try:
            from app.services.rag_retrieve import build_rag_context

            rag_query = "\n".join(
                f"{s.get('name') or ''} {s.get('location') or ''} "
                f"{s.get('description') or ''}".strip()
                for s in scenes
            )
            rag_block = build_rag_context(
                rag_query, top_k=4, type_filter="storyboard"
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
        for attempt in range(2):
            raw, _provider = self.llm.chat(messages)
            try:
                data = self._parse_json(raw)
                frames = data.get("frames")
                if not isinstance(frames, list):
                    raise StoryboardBreakdownError("frames must be list")
                valid = [f for f in frames if isinstance(f, dict)]
                if not valid:
                    raise StoryboardBreakdownError("frames must not be empty")
                for frame in valid:
                    prompt_en = str(frame.get("prompt_en") or "").strip()
                    if not self._is_english_prompt(prompt_en):
                        raise StoryboardBreakdownError(
                            "every frame requires a production-ready English prompt_en"
                        )
                    motion = str(frame.get("motion_prompt_en") or "").strip()
                    if motion and not self._is_english_prompt(motion, min_len=20):
                        raise StoryboardBreakdownError(
                            "motion_prompt_en must be English when provided"
                        )
                expected = {s["id"] for s in scenes}
                covered = {str(f.get("scene_id") or "") for f in valid}
                missing = expected - covered
                if missing:
                    if attempt == 0:
                        raise StoryboardBreakdownError(
                            f"breakdown must include every scene; missing={sorted(missing)}"
                        )
                    by_id = {s["id"]: s for s in scenes}
                    for sid in sorted(missing):
                        valid.append(self._fallback_frame_for_scene(by_id[sid]))
                return valid
            except (StoryboardBreakdownError, json.JSONDecodeError, TypeError) as e:
                last_err = e
                missing_hint = ""
                err_text = str(e)
                if "missing=" in err_text:
                    missing_hint = (
                        " Every input scene id MUST appear in at least one frame.scene_id. "
                        f"Fix coverage: {err_text}."
                    )
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Return ONLY valid JSON. The previous output is invalid. "
                            "every prompt_en must be fluent English, not Chinese. Rewrite all "
                            "prompt_en values as complete Flux/SDXL prompts with subject/action, "
                            "environment, shot/composition, motivated lighting, and physical "
                            "film detail. Include motion_prompt_en (action + one camera move, "
                            "no appearance rewrite) and an English avoid field."
                            f"{missing_hint} "
                            'Schema: {"frames":[{"scene_id":"...","description":"...",'
                            '"description_en":"...","prompt_en":"...",'
                            '"motion_prompt_en":"...","avoid":"...",'
                            '"shot_type":"...","duration":3,"line_ids":[]}]}'
                        ),
                    }
                )
        raise StoryboardBreakdownError(f"invalid breakdown output: {last_err}")

    def _fallback_frame_for_scene(self, scene: dict[str, Any]) -> dict[str, Any]:
        """Deterministic frame when the LLM skips a scene_id."""
        name = (scene.get("name") or scene.get("location") or "scene").strip() or "scene"
        desc = (scene.get("description") or name or "镜头").strip()
        still = (scene.get("description_en") or "").strip()
        if not self._is_english_prompt(still):
            still = (
                f"Medium shot establishing {name}, motivated practical light, "
                "natural materials, eye-level 50mm, live-action film still, mild grain"
            )
        line_ids = [str(ln["id"]) for ln in (scene.get("lines") or []) if ln.get("id")]
        return {
            "scene_id": scene["id"],
            "description": desc,
            "description_en": still,
            "prompt_en": still,
            "motion_prompt_en": (
                "The subject completes one small visible action, then settles. "
                "Camera: locked-off. About 5s. Keep identity, face, hair, and wardrobe "
                "unchanged from the first frame."
            ),
            "avoid": (
                "anime, illustration, cgi, doll skin, face drift, wardrobe change, "
                "extra fingers, text, watermark, deformed hands"
            ),
            "shot_type": "中景",
            "angle": "平视",
            "movement": "固定",
            "duration": 3,
            "line_ids": line_ids,
        }

    @staticmethod
    def _is_english_prompt(value: str, min_len: int = 24) -> bool:
        if len(value) < min_len or not re.search(r"[A-Za-z]{3,}", value):
            return False
        cjk = len(re.findall(r"[\u4e00-\u9fff]", value))
        latin = len(re.findall(r"[A-Za-z]", value))
        return cjk <= 3 and latin >= cjk * 4

    def _parse_json(self, raw: str) -> dict[str, Any]:
        from app.services.json_utils import parse_llm_json

        return parse_llm_json(raw)

    def _apply_plan(
        self,
        project_id: str,
        scenes: list[dict[str, Any]],
        planned: list[dict[str, Any]],
        assets: list[dict[str, Any]],
        *,
        replace_existing: bool,
    ) -> int:
        by_scene = {s["id"]: s for s in scenes}
        line_maps = {
            sid: {ln["id"]: ln for ln in (s.get("lines") or [])}
            for sid, s in by_scene.items()
        }
        used: dict[str, set[str]] = {sid: set() for sid in by_scene}
        created = 0
        created_by_scene: dict[str, list[str]] = {sid: [] for sid in by_scene}

        for p in planned:
            sid = str(p.get("scene_id") or "")
            if sid not in by_scene:
                continue
            line_map = line_maps[sid]
            lines = []
            for lid in p.get("line_ids") or []:
                lid = str(lid)
                if lid in line_map and lid not in used[sid]:
                    lines.append(line_map[lid])
                    used[sid].add(lid)
            scene = by_scene[sid]
            description = str(p.get("description") or scene.get("name") or "镜头")
            description_en = str(p.get("description_en") or "").strip()
            locks = self._locks_for_scene(scene, assets)
            shot_body = str(p.get("prompt_en") or description_en).strip()
            if not self._is_english_prompt(shot_body):
                shot_body = description_en or (
                    "observed live-action still, motivated practical light"
                )
            prompt_en = compose_still_prompt(shot_body, locks)
            draft = {
                "description_en": description_en,
                "description": description,
                "movement": str(p.get("movement") or "固定"),
                "duration": p.get("duration") or 3,
                "motion_prompt_en": str(p.get("motion_prompt_en") or "").strip(),
            }
            motion = resolve_i2v_prompt(draft)
            fr = self.frame_repo.create(
                project_id,
                scene_id=sid,
                scene=scene.get("name") or "",
                character=",".join(str(c) for c in (scene.get("characters") or []) if c),
                description=description,
                description_en=description_en or description,
                prompt_cn=description,
                prompt_en=prompt_en,
                motion_prompt_en=motion,
                negative_prompt=(
                    str(p.get("avoid") or p.get("negative_prompt") or "").strip()
                    or "text, watermark, logo, duplicate person, malformed hands, "
                    "deformed face, inconsistent clothing, blurry, low detail"
                ),
                shot_type=str(p.get("shot_type") or "中景"),
                duration=float(p.get("duration") or 3),
                lines=lines,
            )
            created += 1
            created_by_scene[sid].append(fr["id"])

        # Leftover lines → last frame of scene (or create one)
        for sid, scene in by_scene.items():
            leftover_ids = [i for i in line_maps[sid] if i not in used[sid]]
            leftover = [line_maps[sid][i] for i in leftover_ids]
            if not leftover:
                if not created_by_scene[sid]:
                    desc = scene.get("description") or scene.get("name") or "镜头"
                    still = (
                        (scene.get("description_en") or "").strip()
                        or "establishing still, motivated practical light"
                    )
                    prompt_en = compose_still_prompt(
                        still, self._locks_for_scene(scene, assets)
                    )
                    self.frame_repo.create(
                        project_id,
                        scene_id=sid,
                        scene=scene.get("name") or "",
                        description=desc,
                        description_en=still,
                        prompt_cn=desc,
                        prompt_en=prompt_en,
                        motion_prompt_en=resolve_i2v_prompt(
                            {
                                "description_en": still,
                                "movement": "固定",
                                "duration": 3,
                                "motion_prompt_en": "",
                            }
                        ),
                        lines=[],
                    )
                    created += 1
                continue
            if created_by_scene[sid]:
                last_id = created_by_scene[sid][-1]
                last = self.frame_repo.get(project_id, last_id)
                merged = list(last.get("lines") or []) + leftover
                self.frame_repo.update(project_id, last_id, lines=normalize_lines(merged))
            else:
                desc = scene.get("description") or scene.get("name") or "镜头"
                still = (
                    (scene.get("description_en") or "").strip()
                    or "establishing still, motivated practical light"
                )
                prompt_en = compose_still_prompt(
                    still, self._locks_for_scene(scene, assets)
                )
                self.frame_repo.create(
                    project_id,
                    scene_id=sid,
                    scene=scene.get("name") or "",
                    description=desc,
                    description_en=still,
                    prompt_cn=desc,
                    prompt_en=prompt_en,
                    motion_prompt_en=resolve_i2v_prompt(
                        {
                            "description_en": still,
                            "movement": "固定",
                            "duration": 3,
                            "motion_prompt_en": "",
                        }
                    ),
                    lines=leftover,
                )
                created += 1
        return created
