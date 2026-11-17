from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


STABLE_ERROR_CODES = frozenset(
    {
        "casting_reference_missing",
        "render_request_stale",
        "too_many_strong_identities",
        "look_state_identity_conflict",
        "kontext_model_unavailable",
        "kontext_workflow_unavailable",
        "reference_upload_invalid",
        "comfyui_unavailable",
        "degradation_not_authorized",
        "invalid_rejection_reason",
        "render_attempt_not_found",
        "render_candidate_required",
        "frame_not_found",
        "render_execution_failed",
    }
)


class StoryboardRenderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 422,
        field: str = "",
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        super().__init__(f"{code}: {message}")


class RenderIssue(BaseModel):
    code: str
    message: str
    field: str = ""


class RenderValidation(BaseModel):
    valid: bool
    issues: list[RenderIssue] = Field(default_factory=list)


class CharacterIdentity(BaseModel):
    character_asset_id: str
    character_name: str
    reference_asset_id: str
    reference_image_url: str
    reference_image_hash: str
    identity_anchor: str
    reference_order: int
    legacy_reference: bool = False
    reference_source_type: Literal[
        "auto_crop",
        "manual_crop",
        "upload",
        "generated",
        "legacy_full_reference",
    ] = "legacy_full_reference"
    reference_version: int = 0


class LookState(BaseModel):
    character_asset_id: str
    wardrobe: str = ""
    makeup: str = ""
    hair_state: str = ""
    injury: str = ""
    wetness: str = ""
    dirt: str = ""
    fatigue: str = ""


class RenderPolicy(BaseModel):
    mode: Literal["identity_first"] = "identity_first"
    max_strong_identities: int = 2
    allow_temporary_degradation: bool = False
    identity_priority: list[str] = Field(
        default_factory=lambda: ["face", "age", "hair", "body", "pose", "composition"]
    )


class StoryboardRenderRequest(BaseModel):
    project_id: str
    frame_id: str
    character_identities: list[CharacterIdentity]
    look_states: list[LookState]
    weak_characters: list[str]
    scene_spec: dict[str, Any]
    shot_spec: dict[str, Any]
    render_policy: RenderPolicy
    compiled_prompt: str
    negative_prompt: str
    width: int
    height: int
    source_hash: str
    validation: RenderValidation
