import pytest
from app.services.workflows import SUPPORTED_MODELS, build_workflow


def test_supported_models():
    assert set(SUPPORTED_MODELS) == {"flux"}


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="unknown model"):
        build_workflow("nope", "a cat")


def test_flux_uses_gguf_names():
    wf = build_workflow("flux", "cyberpunk city")
    assert wf["10"]["class_type"] == "UnetLoaderGGUF"
    assert wf["13"]["class_type"] == "DualCLIPLoaderGGUF"
    assert wf["13"]["inputs"]["clip_name2"] == "t5-v1_1-xxl-encoder-Q4_K_S.gguf"
    assert wf["13"]["inputs"]["type"] == "flux"
    assert "CLIPLoaderGGUF" not in {n.get("class_type") for n in wf.values()}
    assert "DualCLIPLoader" not in {n.get("class_type") for n in wf.values()}


def test_flux_injects_resolution():
    wf = build_workflow("flux", "cyberpunk city")
    assert wf["14"]["inputs"]["width"] == 1024
    assert wf["14"]["inputs"]["height"] == 1024


def test_injects_negative_prompt():
    wf = build_workflow("flux", "a red apple", negative_prompt="hdr look, plastic skin")
    assert wf["6"]["inputs"]["text"] == "a red apple"
    assert wf["7"]["inputs"]["text"] == "hdr look, plastic skin"


def test_default_negative_when_empty():
    wf = build_workflow("flux", "x", negative_prompt="")
    assert "blurry" in wf["7"]["inputs"]["text"]
    assert "anime" in wf["7"]["inputs"]["text"]


def test_legacy_models_rejected():
    for model in ("sdxl", "sd15"):
        with pytest.raises(ValueError, match="unknown model"):
            build_workflow(model, "a cat")