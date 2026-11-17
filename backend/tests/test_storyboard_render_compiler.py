from app.services.prompt_ir import ProjectVisualBible
from app.services.storyboard_render.compiler import compile_render_request
from app.services.storyboard_render.types import RenderPolicy


def selected_asset(asset_id: str, name: str) -> dict:
    return {
        "id": asset_id,
        "name": name,
        "type": "character",
        "status": "completed",
        "selection_status": "selected",
        "image_url": f"/media/assets/p1/{asset_id}.png",
        "reference_image_hash": f"sha256:{asset_id}",
        "lock_en": "balanced oval face, almond eyes, natural age impression",
        "identity": {
            "identity_anchor": (
                "balanced oval face, almond eyes, natural age impression"
            )
        },
    }


def visual_bible() -> ProjectVisualBible:
    return ProjectVisualBible(
        casting_aesthetic="polished commercial short-drama actor",
        realism_policy=["natural skin"],
        identity_policy=["stable face and body only"],
        state_policy=["wardrobe and weather are mutable"],
        cinematography=["restrained live action"],
        negative_defaults=["plastic skin"],
    )


def test_compile_preserves_identity_and_applies_look_state():
    result = compile_render_request(
        project_id="p1",
        frame={
            "id": "f1",
            "character": "苏遥",
            "description_en": "Su Yao runs across the alley",
            "shot_type": "medium shot",
            "angle": "eye level",
            "scene_id": "s1",
        },
        scene={
            "id": "s1",
            "location": "rain alley",
            "time": "night",
            "look_states": {
                "asset_suyao": {
                    "wardrobe": "dark wool coat",
                    "wetness": "wet hair ends",
                }
            },
        },
        assets=[selected_asset("asset_suyao", "苏遥")],
        visual_bible=visual_bible(),
        policy=RenderPolicy(),
    )
    assert result.validation.valid is True
    assert result.character_identities[0].reference_asset_id == "asset_suyao"
    assert (
        result.character_identities[0].reference_source_type
        == "legacy_full_reference"
    )
    assert result.character_identities[0].reference_version == 0
    assert result.character_identities[0].legacy_reference is True
    assert "preserve the same facial identity" in result.compiled_prompt.lower()
    assert "dark wool coat" in result.compiled_prompt
    assert "wet hair ends" in result.compiled_prompt
    assert result.negative_prompt == "plastic skin"


def test_compile_prefers_confirmed_purified_identity_reference():
    asset = selected_asset("asset_suyao", "苏遥")
    asset["identity"]["reference"] = {
        "status": "ready",
        "source_type": "manual_crop",
        "image_url": "/media/assets/p1/identity/suyao-v2.png",
        "image_hash": "sha256:purified",
        "version": 2,
    }
    asset["reference_image_hash"] = "sha256:purified-from-disk"

    result = compile_render_request(
        project_id="p1",
        frame={"id": "f1", "character": "苏遥", "scene_id": "s1"},
        scene={"id": "s1", "look_states": {}},
        assets=[asset],
        visual_bible=visual_bible(),
        policy=RenderPolicy(),
    )

    identity = result.character_identities[0]
    assert identity.reference_image_url.endswith("/identity/suyao-v2.png")
    assert identity.reference_image_hash == "sha256:purified-from-disk"
    assert identity.reference_source_type == "manual_crop"
    assert identity.reference_version == 2
    assert identity.legacy_reference is False
    assert "wardrobe, background, pose, and light" in result.compiled_prompt

    asset["identity"]["reference"]["version"] = 3
    changed = compile_render_request(
        project_id="p1",
        frame={"id": "f1", "character": "苏遥", "scene_id": "s1"},
        scene={"id": "s1", "look_states": {}},
        assets=[asset],
        visual_bible=visual_bible(),
        policy=RenderPolicy(),
    )
    assert changed.source_hash != result.source_hash


def test_compile_rejects_identity_terms_inside_look_state():
    scene = {
        "id": "s1",
        "look_states": {"asset_suyao": {"makeup": "change her face shape"}},
    }
    result = compile_render_request(
        project_id="p1",
        frame={"id": "f1", "character": "苏遥", "scene_id": "s1"},
        scene=scene,
        assets=[selected_asset("asset_suyao", "苏遥")],
        visual_bible=visual_bible(),
        policy=RenderPolicy(),
    )
    assert result.validation.valid is False
    assert result.validation.issues[0].code == "look_state_identity_conflict"


def test_third_character_is_text_only_and_hash_is_stable():
    facts = {
        "project_id": "p1",
        "frame": {"id": "f3", "character": "苏遥,林默,路人", "scene_id": "s1"},
        "scene": {"id": "s1", "look_states": {}},
        "assets": [
            selected_asset("asset_suyao", "苏遥"),
            selected_asset("asset_linmo", "林默"),
            selected_asset("asset_extra", "路人"),
        ],
        "visual_bible": visual_bible(),
        "policy": RenderPolicy(),
    }
    first = compile_render_request(**facts)
    second = compile_render_request(**facts)
    assert len(first.character_identities) == 2
    assert [i.character_name for i in first.character_identities] == ["苏遥", "林默"]
    assert [i.reference_order for i in first.character_identities] == [1, 2]
    assert first.weak_characters == ["路人"]
    assert first.source_hash == second.source_hash
    assert "Reference image 1 is 苏遥" in first.compiled_prompt
    assert "Reference image 2 is 林默" in first.compiled_prompt


def test_legacy_reference_and_missing_casting_reference_are_explicit():
    legacy = selected_asset("asset_legacy", "苏遥")
    legacy["selection_status"] = "legacy"
    legacy["identity"] = {}
    result = compile_render_request(
        project_id="p1",
        frame={"id": "f4", "character": "苏遥,林默", "scene_id": "s1"},
        scene={"id": "s1", "look_states": {}},
        assets=[legacy],
        visual_bible=visual_bible(),
        policy=RenderPolicy(),
    )
    assert result.character_identities[0].legacy_reference is True
    assert result.validation.valid is False
    assert any(
        issue.code == "casting_reference_missing" and issue.field == "characters.林默"
        for issue in result.validation.issues
    )
