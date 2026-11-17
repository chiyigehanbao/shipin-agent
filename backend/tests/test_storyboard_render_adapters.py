from pathlib import Path

import pytest

from app.services.storyboard_render.adapters import (
    FluxKontextAdapter,
    TextOnlyFluxAdapter,
)
from app.services.storyboard_render.types import (
    CharacterIdentity,
    RenderPolicy,
    RenderValidation,
    StoryboardRenderError,
    StoryboardRenderRequest,
)


def valid_request(identity_count: int = 1) -> StoryboardRenderRequest:
    identities = [
        CharacterIdentity(
            character_asset_id=f"asset_{index}",
            character_name=f"角色{index}",
            reference_asset_id=f"asset_{index}",
            reference_image_url=f"/media/assets/p1/asset_{index}.png",
            reference_image_hash=f"sha256:asset_{index}",
            identity_anchor="balanced face and stable age impression",
            reference_order=index,
        )
        for index in range(1, identity_count + 1)
    ]
    return StoryboardRenderRequest(
        project_id="p1",
        frame_id="f1",
        character_identities=identities,
        look_states=[],
        weak_characters=[],
        scene_spec={"location": "rain alley"},
        shot_spec={"shot_type": "medium"},
        render_policy=RenderPolicy(),
        compiled_prompt="Preserve identity and change the background to a rain alley.",
        negative_prompt="plastic skin",
        width=1216,
        height=832,
        source_hash="source-1",
        validation=RenderValidation(valid=True),
    )


def ready_model_dir(tmp_path: Path) -> Path:
    models = tmp_path / "models"
    for relative in (
        "unet/flux1-kontext-dev-Q4_K_S.gguf",
        "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
        "clip/clip_l.safetensors",
        "vae/ae.safetensors",
    ):
        path = models / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test-model")
    return models


def test_kontext_adapter_fills_one_reference():
    workflow = FluxKontextAdapter().build(
        request=valid_request(identity_count=1),
        uploaded_images=["suyao.png"],
        seed=42,
    )
    assert workflow["4"]["inputs"]["image"] == "suyao.png"
    assert workflow["7"]["inputs"]["text"] == valid_request(1).compiled_prompt
    assert workflow["3"]["inputs"]["seed"] == 42
    assert workflow["10"]["inputs"]["unet_name"] == (
        "flux1-kontext-dev-Q4_K_S.gguf"
    )


def test_kontext_adapter_chains_second_reference():
    workflow = FluxKontextAdapter().build(
        request=valid_request(identity_count=2),
        uploaded_images=["suyao.png", "linmo.png"],
        seed=43,
    )
    assert workflow["20"]["class_type"] == "LoadImage"
    assert workflow["23"]["class_type"] == "ReferenceLatent"
    assert workflow["23"]["inputs"]["conditioning"] == ["8", 0]
    assert workflow["9"]["inputs"]["conditioning"] == ["23", 0]


def test_text_adapter_requires_explicit_degradation():
    request = valid_request(identity_count=1)
    with pytest.raises(StoryboardRenderError, match="degradation_not_authorized"):
        TextOnlyFluxAdapter().build(request=request, uploaded_images=[], seed=44)


def test_kontext_preflight_reports_missing_core_node(tmp_path: Path):
    readiness = FluxKontextAdapter().preflight(
        request=valid_request(),
        models_dir=ready_model_dir(tmp_path),
        available_node_types={"LoadImage", "VAEEncode", "KSampler"},
    )
    assert readiness.ready is False
    assert "ReferenceLatent" in readiness.missing_nodes


def test_kontext_build_rejects_mismatched_reference_uploads():
    with pytest.raises(StoryboardRenderError, match="reference_upload_invalid"):
        FluxKontextAdapter().build(
            request=valid_request(identity_count=2),
            uploaded_images=["only-one.png"],
            seed=45,
        )
