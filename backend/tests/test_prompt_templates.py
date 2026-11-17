from app.services.prompt_templates import (
    list_templates,
    sampler_overrides_for_model,
    template_for_asset_type,
)
from app.services.workflows import build_workflow


def test_character_template_is_clear_face_v3():
    chars = list_templates(category="character")
    assert chars
    lead = next(t for t in chars if t["id"] == "tpl_001")
    assert "清晰脸" in lead["name"] or "clear" in lead["name_en"].lower()
    assert lead["default_steps"] == 24
    assert lead["default_cfg"] == 1.0
    assert "anime" in (lead["negative_prompt_en"] or "")
    assert "高清细节" not in lead["user_prompt_cn"]


def test_script_template_leads_and_has_drama_rules():
    scripts = list_templates(category="script")
    assert scripts
    s = scripts[0]
    assert s["id"] == "tpl_004"
    assert "短剧" in s["name"] or "钩子" in s["system_prompt_cn"]
    assert "外貌" in s["system_prompt_cn"] or "定妆" in s["system_prompt_cn"]
    assert "lines" in s["user_prompt_cn"]
    assert list_templates()[0]["category"] == "script"


def test_script_expand_pack_has_short_drama_rules():
    from pathlib import Path

    pack = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "prompt_packs"
        / "script_expand_v1"
        / "system.md"
    ).read_text(encoding="utf-8")
    assert "钩子" in pack
    assert "场场有增量" in pack or "增量" in pack
    assert "五官" in pack or "外貌" in pack
    assert "JSON" in pack


def test_flux_overrides_from_character_template():
    tpl = template_for_asset_type("character")
    ov = sampler_overrides_for_model(tpl, "flux")
    assert ov["steps"] == 24
    assert ov["cfg"] == 1.0
    assert ov["sampler_name"] == "euler"
    wf = build_workflow("flux", "a portrait", "", **ov)
    assert wf["3"]["inputs"]["steps"] == 24
    assert wf["3"]["inputs"]["cfg"] == 1.0
    assert "anime" in wf["7"]["inputs"]["text"] or "blurry" in wf["7"]["inputs"]["text"]


def test_flux_overrides_ignore_model_arg():
    tpl = template_for_asset_type("character")
    for model in ("flux", "sdxl", "sd15"):
        ov = sampler_overrides_for_model(tpl, model)
        assert ov["steps"] == 24
        assert ov["cfg"] == 1.0
        assert ov["sampler_name"] == "euler"
