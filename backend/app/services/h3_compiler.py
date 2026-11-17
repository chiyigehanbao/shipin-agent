from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.db.repositories.assets import AssetRepository
from app.db.repositories.compiled_prompts import CompiledPromptRepository
from app.db.repositories.frames import FrameRepository
from app.db.repositories.projects import ProjectRepository
from app.db.repositories.scenes import SceneRepository
from app.db.repositories.visual_specs import VisualSpecRepository
from app.services.h3_guide import GUIDE_VERSION, load_base_guide
from app.services.h3_validator import validate_h3_prompt
from app.services.llm_provider import LLMProvider
from app.services.prompt_ir import H3SourceContext
from app.services.visual_bible import VisualBibleService


def canonical_source_hash(context: H3SourceContext) -> str:
    payload = json.dumps(
        context.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _strip_markdown_fence(raw: str) -> str:
    text = (raw or "").strip()
    match = re.fullmatch(r"```(?:text|markdown)?\s*(.*?)\s*```", text, re.DOTALL)
    return match.group(1).strip() if match else text


def _dialogue_texts(context: H3SourceContext) -> list[str]:
    return [
        str(line.get("text") or "")
        for line in context.dialogue
        if str(line.get("text") or "").strip()
    ]


class H3PromptCompiler:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        compiled_repo: CompiledPromptRepository | None = None,
        visual_repo: VisualSpecRepository | None = None,
        project_repo: ProjectRepository | None = None,
        scene_repo: SceneRepository | None = None,
        asset_repo: AssetRepository | None = None,
        frame_repo: FrameRepository | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.llm = llm
        self.compiled_repo = compiled_repo or CompiledPromptRepository(db_path)
        self.visual_repo = visual_repo or VisualSpecRepository(db_path)
        self.project_repo = project_repo or ProjectRepository(db_path)
        self.scene_repo = scene_repo or SceneRepository(db_path)
        self.asset_repo = asset_repo or AssetRepository(db_path)
        self.frame_repo = frame_repo or FrameRepository(db_path)
        self.visual_bible = VisualBibleService(self.visual_repo)

    def compile_context(
        self,
        *,
        project_id: str,
        source_type: str,
        source_id: str,
        context: H3SourceContext,
    ) -> dict[str, Any]:
        source_hash = canonical_source_hash(context)
        expected_dialogue = _dialogue_texts(context)
        messages = self._compile_messages(context)
        raw, provider = self.llm.chat(messages)
        content = _strip_markdown_fence(raw)
        report = validate_h3_prompt(
            content,
            mode=context.mode,
            duration_sec=context.duration_sec,
            expected_dialogue=expected_dialogue,
        )
        if not report.valid:
            repair_messages = messages + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Repair the prompt and return only the complete corrected H3 prompt. "
                        "Do not change any dialogue. Validation issues:\n"
                        + json.dumps(
                            [issue.model_dump() for issue in report.issues],
                            ensure_ascii=False,
                        )
                    ),
                },
            ]
            raw, provider = self.llm.chat(repair_messages)
            content = _strip_markdown_fence(raw)
            report = validate_h3_prompt(
                content,
                mode=context.mode,
                duration_sec=context.duration_sec,
                expected_dialogue=expected_dialogue,
            )
        row = self.compiled_repo.create(
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            target_model="minimax-h3",
            mode=context.mode,
            source_hash=source_hash,
            guide_version=GUIDE_VERSION,
            content=content,
            validation=report.model_dump(),
            provider=provider,
        )
        row["stale"] = False
        return row

    def compile_frame(
        self,
        project_id: str,
        frame_id: str,
        *,
        mode: str = "i2va",
        duration_sec: float = 5.17,
    ) -> dict[str, Any]:
        if mode.lower() != "i2va":
            raise ValueError("frame compilation only supports i2va")
        return self.compile_context(
            project_id=project_id,
            source_type="frame",
            source_id=frame_id,
            context=self.frame_context(project_id, frame_id, duration_sec=duration_sec),
        )

    def compile_t2va(
        self,
        project_id: str,
        brief: str,
        *,
        duration_sec: float,
        source_id: str = "project",
    ) -> dict[str, Any]:
        context = self.t2va_context(project_id, brief, duration_sec=duration_sec)
        return self.compile_context(
            project_id=project_id,
            source_type="project",
            source_id=source_id,
            context=context,
        )

    def t2va_context(
        self, project_id: str, brief: str, *, duration_sec: float
    ) -> H3SourceContext:
        project = self.project_repo.get(project_id) or {
            "id": project_id,
            "name": project_id,
            "description": "",
            "style": "",
        }
        return H3SourceContext(
            mode="t2va",
            duration_sec=duration_sec,
            project=project,
            visual_bible=self.visual_bible.get(project_id),
            shot={"creative_brief": (brief or "").strip()},
        )

    def frame_context(
        self, project_id: str, frame_id: str, *, duration_sec: float
    ) -> H3SourceContext:
        project = self.project_repo.get(project_id)
        if not project:
            raise KeyError(project_id)
        frame = self.frame_repo.get(project_id, frame_id)
        if not frame:
            raise KeyError(frame_id)
        scenes = self.scene_repo.list_by_project(project_id)
        scene = next(
            (
                item
                for item in scenes
                if item.get("id") == frame.get("scene_id")
                or item.get("name") == frame.get("scene")
            ),
            {},
        )
        character_names = {
            value.strip()
            for value in str(frame.get("character") or "").split(",")
            if value.strip()
        }
        subjects = []
        for asset in self.asset_repo.list(project_id):
            is_character = asset.get("type") == "character" and asset.get("name") in character_names
            is_scene = asset.get("type") == "scene" and asset.get("name") == frame.get("scene")
            if not (is_character or is_scene):
                continue
            subjects.append(
                {
                    "name": asset.get("name") or "",
                    "type": asset.get("type") or "",
                    "identity_or_scene_anchor": asset.get("lock_en") or "",
                    "reference_image": asset.get("image_url"),
                    "selection_status": asset.get("selection_status") or "legacy",
                }
            )
        shot = {
            key: frame.get(key)
            for key in (
                "number",
                "description",
                "description_en",
                "shot_type",
                "angle",
                "movement",
                "duration",
                "motion_prompt_en",
                "image_url",
            )
        }
        return H3SourceContext(
            mode="i2va",
            duration_sec=duration_sec,
            project=project,
            visual_bible=self.visual_bible.get(project_id),
            subjects=subjects,
            scene=scene,
            shot=shot,
            dialogue=frame.get("lines") or [],
            soundscape="Infer only concrete ambience and physical sounds from the scene and action.",
            music="N/A unless the project or shot explicitly requests audience-only music.",
        )

    def latest_frame(
        self, project_id: str, frame_id: str, *, duration_sec: float
    ) -> dict[str, Any] | None:
        row = self.compiled_repo.latest(project_id, "frame", frame_id, "i2va")
        if row is None:
            return None
        current_hash = canonical_source_hash(
            self.frame_context(project_id, frame_id, duration_sec=duration_sec)
        )
        row["stale"] = row["source_hash"] != current_hash
        return row

    @staticmethod
    def _compile_messages(context: H3SourceContext) -> list[dict[str, str]]:
        system = (
            "You compile production data into MiniMax H3 prompts. Follow the official "
            "guide below exactly. Return only the final prompt, without Markdown fences "
            "or commentary. Preserve dialogue and visible text verbatim. Never invent a "
            "reference label that is absent from the input.\n\n"
            + load_base_guide()
        )
        user = (
            "Compile this deterministic project context. The effective duration is binding.\n"
            + json.dumps(
                context.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
