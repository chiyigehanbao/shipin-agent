from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from app.services.prompt_ir import ProjectVisualBible
from app.services.storyboard_render.types import (
    CharacterIdentity,
    LookState,
    RenderIssue,
    RenderPolicy,
    RenderValidation,
    StoryboardRenderRequest,
)


IDENTITY_CONFLICT_TERMS = (
    "face shape",
    "facial geometry",
    "different age",
    "younger",
    "older",
    "different person",
    "body type",
    "脸型",
    "面部结构",
    "五官比例",
    "不同年龄",
    "变年轻",
    "变老",
    "换人",
    "不同的人",
    "体型",
)

LOOK_FIELDS = (
    "wardrobe",
    "makeup",
    "hair_state",
    "injury",
    "wetness",
    "dirt",
    "fatigue",
)


def _character_names(frame: dict[str, Any]) -> list[str]:
    raw = frame.get("characters") or frame.get("character") or ""
    values = raw if isinstance(raw, list) else re.split(r"[,，、/]+", str(raw))
    names: list[str] = []
    for value in values:
        name = str(value).strip()
        if name and name not in names:
            names.append(name)
    return names


def _eligible_reference(asset: dict[str, Any]) -> bool:
    if asset.get("type") != "character":
        return False
    if asset.get("status") != "completed" or not asset.get("image_url"):
        return False
    selection = asset.get("selection_status") or "legacy"
    if selection == "selected":
        identity = asset.get("identity") or {}
        return bool(identity.get("identity_anchor") or asset.get("lock_en"))
    return selection == "legacy" and bool(str(asset.get("lock_en") or "").strip())


def _reference_for_name(
    assets: list[dict[str, Any]], character_name: str
) -> dict[str, Any] | None:
    matches = [
        asset
        for asset in assets
        if str(asset.get("name") or "").strip() == character_name
        and _eligible_reference(asset)
    ]
    matches.sort(
        key=lambda item: (
            0 if item.get("selection_status") == "selected" else 1,
            str(item.get("id") or ""),
        )
    )
    return matches[0] if matches else None


def _selected_reference(asset: dict[str, Any]) -> tuple[str, str, int, bool]:
    reference = (asset.get("identity") or {}).get("reference") or {}
    if reference.get("status") == "ready" and reference.get("image_url"):
        return (
            str(reference["image_url"]),
            str(reference.get("source_type") or "manual_crop"),
            int(reference.get("version") or 1),
            False,
        )
    return str(asset.get("image_url") or ""), "legacy_full_reference", 0, True


def _identity_from_asset(
    asset: dict[str, Any], character_name: str, reference_order: int
) -> CharacterIdentity:
    identity = asset.get("identity") or {}
    image_url, source_type, version, legacy = _selected_reference(asset)
    return CharacterIdentity(
        character_asset_id=str(asset["id"]),
        character_name=character_name,
        reference_asset_id=str(asset["id"]),
        reference_image_url=image_url,
        reference_image_hash=str(asset.get("reference_image_hash") or ""),
        identity_anchor=str(
            identity.get("identity_anchor") or asset.get("lock_en") or ""
        ).strip(),
        reference_order=reference_order,
        legacy_reference=legacy,
        reference_source_type=source_type,
        reference_version=version,
    )


def _look_state(
    identity: CharacterIdentity, scene: dict[str, Any]
) -> LookState:
    stored = (scene.get("look_states") or {}).get(identity.character_asset_id) or {}
    values = {key: str(stored.get(key) or "").strip() for key in LOOK_FIELDS}
    return LookState(character_asset_id=identity.character_asset_id, **values)


def _conflict_issues(look_states: list[LookState]) -> list[RenderIssue]:
    issues: list[RenderIssue] = []
    for state in look_states:
        for field in LOOK_FIELDS:
            value = str(getattr(state, field) or "")
            lower = value.lower()
            term = next((token for token in IDENTITY_CONFLICT_TERMS if token in lower), None)
            if term:
                issues.append(
                    RenderIssue(
                        code="look_state_identity_conflict",
                        message=f"场景外观状态不能修改人物永久身份：{term}",
                        field=f"look_states.{state.character_asset_id}.{field}",
                    )
                )
    return issues


def reference_binding_text(identities: list[CharacterIdentity]) -> str:
    if not identities:
        return ""
    positions = ("primary/left subject", "secondary/right subject")
    return " ".join(
        f"Reference image {item.reference_order} is {item.character_name}; bind it only "
        f"to the {positions[index]}."
        for index, item in enumerate(identities)
    )


def identity_preservation_text(identities: list[CharacterIdentity]) -> str:
    return " ".join(
        f"Preserve the same facial identity for {item.character_name}. Use reference "
        f"image {item.reference_order} only to constrain facial identity, age impression, "
        f"and stable hair. Take wardrobe, "
        f"background, pose, and light exclusively from the current request. Identity "
        f"anchor: {item.identity_anchor}."
        for item in identities
    )


def allowed_look_changes_text(
    identities: list[CharacterIdentity], look_states: list[LookState]
) -> str:
    names = {item.character_asset_id: item.character_name for item in identities}
    statements: list[str] = []
    for state in look_states:
        changes = [
            f"{field.replace('_', ' ')}: {getattr(state, field)}"
            for field in LOOK_FIELDS
            if getattr(state, field)
        ]
        if changes:
            statements.append(
                f"For {names.get(state.character_asset_id, state.character_asset_id)}, "
                f"allow only these scene-specific appearance changes: {', '.join(changes)}."
            )
    if not statements:
        return "No scene-specific identity or appearance changes are authorized."
    return " ".join(statements)


def _dict_text(label: str, values: dict[str, Any]) -> str:
    facts = [
        f"{key.replace('_', ' ')}: {value}"
        for key, value in values.items()
        if value not in (None, "", [], {})
    ]
    return f"{label}: " + "; ".join(facts) if facts else ""


def scene_text(scene_spec: dict[str, Any]) -> str:
    return _dict_text("Scene", scene_spec)


def shot_text(shot_spec: dict[str, Any]) -> str:
    return _dict_text("Shot", shot_spec)


def _scene_spec(
    scene: dict[str, Any],
    assets: list[dict[str, Any]],
    visual_bible: ProjectVisualBible,
) -> dict[str, Any]:
    spec = {
        key: scene.get(key)
        for key in (
            "name",
            "location",
            "time",
            "weather",
            "description_en",
            "prompt_en",
        )
        if scene.get(key) not in (None, "")
    }
    scene_asset = next(
        (
            asset
            for asset in sorted(assets, key=lambda item: str(item.get("id") or ""))
            if asset.get("type") == "scene"
            and (
                asset.get("name") == scene.get("name")
                or asset.get("name") == scene.get("location")
            )
            and asset.get("lock_en")
        ),
        None,
    )
    if scene_asset:
        spec["location_anchor"] = scene_asset["lock_en"]
    spec["cinematography"] = list(visual_bible.cinematography)
    spec["realism_policy"] = list(visual_bible.realism_policy)
    return spec


def _shot_spec(frame: dict[str, Any], weak_characters: list[str]) -> dict[str, Any]:
    spec = {
        key: frame.get(key)
        for key in (
            "description",
            "description_en",
            "shot_type",
            "angle",
            "movement",
            "duration",
            "prompt_en",
        )
        if frame.get(key) not in (None, "")
    }
    if weak_characters:
        spec["background_characters"] = weak_characters
        spec["background_character_policy"] = "text-only extras without strong identity references"
    return spec


def _negative_prompt(*values: Iterable[str] | str) -> str:
    tokens: list[str] = []
    for value in values:
        source = [value] if isinstance(value, str) else value
        for item in source:
            for token in str(item or "").split(","):
                cleaned = token.strip()
                if cleaned and cleaned not in tokens:
                    tokens.append(cleaned)
    return ", ".join(tokens)


def _source_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compile_render_request(
    *,
    project_id: str,
    frame: dict[str, Any],
    scene: dict[str, Any],
    assets: list[dict[str, Any]],
    visual_bible: ProjectVisualBible,
    policy: RenderPolicy,
) -> StoryboardRenderRequest:
    character_names = _character_names(frame)
    strong_limit = max(0, min(policy.max_strong_identities, 2))
    strong_names = character_names[:strong_limit]
    weak_characters = character_names[strong_limit:]
    identities: list[CharacterIdentity] = []
    issues: list[RenderIssue] = []
    for name in strong_names:
        asset = _reference_for_name(assets, name)
        if asset is None:
            issues.append(
                RenderIssue(
                    code="casting_reference_missing",
                    message=f"角色“{name}”缺少已选定且生成成功的定妆参考图",
                    field=f"characters.{name}",
                )
            )
            continue
        identity = _identity_from_asset(asset, name, len(identities) + 1)
        identities.append(identity)
        if not identity.reference_image_hash:
            issues.append(
                RenderIssue(
                    code="reference_upload_invalid",
                    message=f"角色“{name}”的参考图缺少内容哈希",
                    field=f"characters.{name}.reference_image_hash",
                )
            )
    look_states = [_look_state(identity, scene) for identity in identities]
    issues = _conflict_issues(look_states) + issues
    scene_spec = _scene_spec(scene, assets, visual_bible)
    shot_spec = _shot_spec(frame, weak_characters)
    parts = [
        reference_binding_text(identities),
        identity_preservation_text(identities),
        allowed_look_changes_text(identities, look_states),
        scene_text(scene_spec),
        shot_text(shot_spec),
        (
            "Identity and refined natural appearance take priority. "
            "If pose or composition conflicts with identity preservation, allow a small pose "
            "or framing deviation while keeping the same face, age impression, hairstyle, and build."
        ),
    ]
    compiled_prompt = "\n\n".join(part for part in parts if part.strip())
    negative_prompt = _negative_prompt(
        visual_bible.negative_defaults,
        str(frame.get("negative_prompt") or ""),
    )
    width = int(frame.get("width") or 1216)
    height = int(frame.get("height") or 832)
    hash_payload = {
        "project_id": project_id,
        "frame_id": str(frame.get("id") or ""),
        "character_identities": [item.model_dump(mode="json") for item in identities],
        "look_states": [item.model_dump(mode="json") for item in look_states],
        "weak_characters": weak_characters,
        "scene_spec": scene_spec,
        "shot_spec": shot_spec,
        "render_policy": policy.model_dump(mode="json"),
        "visual_bible": visual_bible.model_dump(mode="json"),
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
    }
    return StoryboardRenderRequest(
        project_id=project_id,
        frame_id=str(frame.get("id") or ""),
        character_identities=identities,
        look_states=look_states,
        weak_characters=weak_characters,
        scene_spec=scene_spec,
        shot_spec=shot_spec,
        render_policy=policy,
        compiled_prompt=compiled_prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        source_hash=_source_hash(hash_payload),
        validation=RenderValidation(valid=not issues, issues=issues),
    )
