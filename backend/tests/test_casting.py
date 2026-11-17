import json
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.casting import CASTING_NEGATIVE_PROMPT, CastingService


client = TestClient(app)


class FakeLLM:
    def __init__(self, text: str):
        self.text = text

    def chat(self, messages):
        return self.text, "fake"


REFERENCE_STRUCTURE_PHRASES = (
    "credible refined leading-actor presence with individual facial character",
    "clean natural brows and attentive eyes",
    "believable hairline, separated hair strands and a few flyaways",
    "faint natural under-eye texture and nasolabial structure",
    "continuous diffuse tonal response across forehead, nose bridge and cheeks",
    "3:4 vertical chest-up actor comparison portrait",
    "complete head and shoulders",
    "70mm lens at f/8",
    "natural facial perspective",
    "broad indirect daylight from above and to one side",
    "white bounce fill",
    "subtle fine photographic grain",
)


def realistic_prompt(anchor: str) -> str:
    return (
        "unretouched adult actor casting photograph, "
        f"permanent facial identity: {anchor}, believable age, "
        "credible refined leading-actor presence with individual facial character, "
        "graceful facial planes, clean natural brows and attentive eyes, "
        "stable natural hairstyle, believable hairline, separated hair strands and a few flyaways, "
        "neutral rested expression, matte skin response, visible natural pores and fine facial texture, "
        "subtle uneven skin tone, minor facial asymmetry, "
        "faint natural under-eye texture and nasolabial structure, "
        "bare-faced with naturally pigmented dry lips, visible fine facial hair and a few faint blemishes, "
        "dry low-reflectance skin surface, diffuse skin color with gentle tonal falloff, "
        "continuous diffuse tonal response across forehead, nose bridge and cheeks, "
        "plain medium-gray crew-neck cotton top with shoulders covered, "
        "3:4 vertical chest-up actor comparison portrait, complete head and shoulders, "
        "centered eye-level camera, 70mm lens at f/8, natural facial perspective, "
        "both eyes and all facial planes equally resolved, "
        "broad indirect daylight from above and to one side, white bounce fill, "
        "neutral gray background, normal exposure, neutral color response, restrained contrast, "
        "subtle fine photographic grain, "
        "identical camera distance, exposure, light placement and comparison framing"
    )


def test_casting_service_accepts_four_distinct_unretouched_candidates():
    candidates = [
        {
            "label": f"真实方案{i}",
            "identity_anchor": f"distinct permanent facial geometry {i}",
            "prompt_en": realistic_prompt(f"distinct permanent facial geometry {i}"),
        }
        for i in range(1, 5)
    ]
    concepts = CastingService(
        llm=FakeLLM(json.dumps({"candidates": candidates}))
    ).generate(
        name="苏遥",
        brief="都市悬疑剧女主，28岁，聪明克制",
    )

    assert [item.label for item in concepts] == [f"真实方案{i}" for i in range(1, 5)]
    assert len({c.identity_anchor for c in concepts}) == 4
    assert all("unretouched adult actor casting photograph" in c.prompt_en for c in concepts)
    assert all("matte skin response" in c.prompt_en for c in concepts)
    assert all("70mm lens at f/8" in c.prompt_en for c in concepts)


@pytest.mark.parametrize(
    "beauty_trigger",
    [
        "polished commercial",
        "pale skin",
        "flawless skin",
        "perfect skin",
        "beauty lighting",
        "soft frontal studio light",
        "harmonious distinctive features",
        "85mm portrait",
    ],
)
def test_casting_service_rejects_beauty_retouched_llm_prompts(beauty_trigger):
    candidates = [
        {
            "label": f"污染方案{i}",
            "identity_anchor": f"face geometry {i}",
            "prompt_en": f"{realistic_prompt(f'face geometry {i}')}, {beauty_trigger}",
        }
        for i in range(1, 5)
    ]
    concepts = CastingService(
        llm=FakeLLM(json.dumps({"candidates": candidates}))
    ).generate(
        name="苏遥",
        brief="女主",
    )

    assert all(item.label != "污染方案1" for item in concepts)
    assert all(beauty_trigger not in item.prompt_en.lower() for item in concepts)


@pytest.mark.parametrize(
    "trigger",
    [
        "porcelain skin",
        "translucent skin",
        "water-gloss lips",
        "wet lips",
        "bloom",
        "halation",
        "beauty filter",
        "soft-focus beauty",
        "strong rim light",
        "extremely shallow depth of field",
        "8K",
        "HDR",
    ],
)
def test_casting_service_rejects_reference_style_surface_triggers(trigger):
    candidates = [
        {
            "label": f"污染方案{i}",
            "identity_anchor": f"distinct permanent facial geometry {i}",
            "prompt_en": f"{realistic_prompt(f'distinct permanent facial geometry {i}')}, {trigger}",
        }
        for i in range(1, 5)
    ]

    concepts = CastingService(
        llm=FakeLLM(json.dumps({"candidates": candidates}))
    ).generate(name="苏晚", brief="女主")

    assert all(item.label != "污染方案1" for item in concepts)
    assert all(trigger.lower() not in item.prompt_en.lower() for item in concepts)


def test_fallback_sanitizes_chinese_reference_beauty_language():
    concepts = CastingService(llm=FakeLLM("not json")).generate(
        name="苏晚",
        brief="清冷女主 冷白瓷肌 水光唇 柔焦美颜 强轮廓光 极浅景深 | mid-20s East Asian woman",
    )
    combined = " ".join(item.prompt_en.lower() for item in concepts)

    assert "冷白瓷肌" not in combined
    assert "水光唇" not in combined
    assert "柔焦美颜" not in combined
    assert "强轮廓光" not in combined
    assert "极浅景深" not in combined


def test_fallback_removes_legacy_beauty_phrases_from_source_brief():
    concepts = CastingService(llm=FakeLLM("not json")).generate(
        name="苏晚",
        brief=(
            "polished commercial short-drama actor | pale skin | "
            "harmonious distinctive features | soft frontal studio light | 85mm portrait"
        ),
    )
    combined = " ".join(item.prompt_en.lower() for item in concepts)

    assert "polished" not in combined
    assert "pale skin" not in combined
    assert "soft frontal studio light" not in combined
    assert "85mm" not in combined
    assert all(
        "visible natural pores and fine facial texture" in item.prompt_en
        for item in concepts
    )
    assert all(
        "dry low-reflectance skin surface" in item.prompt_en
        for item in concepts
    )


def test_fallback_keeps_demographics_without_legacy_face_or_capture_prompt():
    concepts = CastingService(llm=FakeLLM("not json")).generate(
        name="苏晚",
        brief=(
            "凛冽冷艳 | polished commercial short-drama actor, "
            "mid-20s East Asian woman, slight build, high sharp cheekbones, "
            "narrow oval jawline, straight black hair, natural skin, neutral gray background | "
            "high sharp cheekbones, narrow oval jawline, dark almond eyes with heavy upper lids"
        ),
    )
    combined = " ".join(item.prompt_en.lower() for item in concepts)

    assert "mid-20s" in combined
    assert "east asian woman" in combined
    assert "slight build" in combined
    assert "commercial short-drama actor" not in combined
    assert "natural skin" not in combined
    assert "high sharp cheekbones" not in combined
    assert "heavy upper lids" not in combined


def test_fallback_uses_reference_informed_actor_comparison_structure():
    concepts = CastingService(llm=FakeLLM("not json")).generate(
        name="苏晚",
        brief="凛冽冷艳 | mid-20s East Asian woman, slight build",
    )

    assert len(concepts) == 4
    for concept in concepts:
        prompt = concept.prompt_en.lower()
        assert all(phrase.lower() in prompt for phrase in REFERENCE_STRUCTURE_PHRASES)
        assert "50mm lens" not in prompt
        assert "large diffused key light" not in prompt


def test_fallback_positive_prompt_keeps_skin_dry_diffuse_and_facial_detail_visible():
    concepts = CastingService(llm=FakeLLM("not json")).generate(
        name="苏晚",
        brief="凛冽冷艳 | mid-20s East Asian woman, slight build",
    )

    for concept in concepts:
        prompt = concept.prompt_en.lower()
        assert "bare-faced with naturally pigmented dry lips" in prompt
        assert "dry low-reflectance skin surface" in prompt
        assert "diffuse skin color with gentle tonal falloff" in prompt
        assert "faint natural under-eye texture and nasolabial structure" in prompt
        assert "specular" not in prompt
        assert "highlight" not in prompt
        assert "glow" not in prompt
        assert "grooming" not in prompt


def test_casting_negative_prompt_targets_observed_face_failures():
    negative = CASTING_NEGATIVE_PROMPT.lower()
    required = (
        "broad forehead sheen",
        "white nose bridge stripe",
        "glossy cheek patches",
        "foundation-covered pores",
        "obvious blush",
        "lipstick",
        "lip gloss",
        "facial contouring",
        "perfect facial symmetry",
        "cropped head",
        "cropped shoulders",
    )

    assert all(phrase in negative for phrase in required)


def test_casting_service_falls_back_when_llm_encodes_temporary_state():
    bad = {
        "candidates": [
            {
                "label": f"方案{i}",
                "identity_anchor": f"face {i}",
                "prompt_en": f"polished commercial short-drama actor, wet with rain, face {i}",
            }
            for i in range(1, 5)
        ]
    }
    concepts = CastingService(llm=FakeLLM(json.dumps(bad))).generate(
        name="苏遥",
        brief="女主",
    )

    forbidden = ("rain", "wet", "blood", "mud", "exhausted", "sweat")
    assert len(concepts) == 4
    assert all(
        not any(
            re.search(rf"\b{re.escape(word)}\b", concept.prompt_en.lower())
            for word in forbidden
        )
        for concept in concepts
    )


def test_cast_endpoint_reuses_source_and_enqueues_exactly_four_candidates():
    source = {
        "id": "asset_c_source",
        "project_id": "p_cast",
        "name": "苏遥",
        "name_en": "苏遥",
        "type": "character",
        "status": "pending",
        "prompt_cn": "都市悬疑女主",
        "prompt_en": "urban mystery heroine",
        "negative_prompt": "",
        "lock_en": "",
        "model": "flux",
        "aspect": "portrait",
        "image_url": None,
        "error": None,
        "created_at": "t",
        "candidate_group_id": None,
        "candidate_index": None,
        "selection_status": "legacy",
    }
    concepts = [
        type(
            "Concept",
            (),
            {
                "label": f"方案{i}",
                "identity_anchor": f"anchor {i}",
                "prompt_en": f"polished commercial short-drama actor, anchor {i}",
            },
        )()
        for i in range(1, 5)
    ]
    with patch("app.api.assets.store.get", return_value=source):
        with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
            with patch("app.api.assets.client.health", return_value=True):
                with patch("app.api.assets.get_casting_service") as factory:
                    factory.return_value.generate.return_value = concepts
                    with patch("app.api.assets.store.update") as update:
                        update.side_effect = lambda project_id, asset_id, **fields: {
                            **source,
                            **fields,
                        }
                        with patch("app.api.assets.store.create") as create:
                            create.side_effect = lambda **fields: {
                                **source,
                                "id": f"asset_c_{fields['candidate_index']}",
                                **fields,
                            }
                            with patch("app.api.assets.queue.enqueue") as enqueue:
                                with patch("app.api.assets.job_repo") as jobs:
                                    jobs.create.side_effect = lambda **kw: {"id": f"job_{kw['payload']['asset_id']}"}
                                    response = client.post(
                                        "/api/assets/p_cast/characters/asset_c_source/cast"
                                    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_group_id"]
    assert len(body["candidates"]) == 4
    assert update.call_args.kwargs["candidate_index"] == 1
    assert update.call_args.kwargs["selection_status"] == "candidate"
    assert body["candidates"][0]["identity"]["identity_anchor"] == "anchor 1"
    assert body["candidates"][0]["identity"]["stable_traits"] == [
        "facial_geometry",
        "age_impression",
        "stable_hairstyle",
        "body_build",
    ]
    assert create.call_count == 3
    assert all("image_url" not in call.kwargs for call in create.call_args_list)
    assert all("error" not in call.kwargs for call in create.call_args_list)
    assert enqueue.call_count == 4


def test_recasting_existing_candidate_creates_new_group_without_overwriting_history():
    source = {
        "id": "asset_old_1",
        "project_id": "p_recast",
        "name": "苏晚",
        "name_en": "Su Wan",
        "type": "character",
        "status": "completed",
        "prompt_cn": "旧方案1",
        "prompt_en": "legacy portrait",
        "negative_prompt": "",
        "lock_en": "old anchor 1",
        "model": "flux",
        "aspect": "portrait",
        "image_url": "/media/old-1.png",
        "error": None,
        "created_at": "t",
        "candidate_group_id": "cast_old",
        "candidate_index": 1,
        "selection_status": "selected",
    }
    old_group = [
        {**source, "id": f"asset_old_{i}", "candidate_index": i}
        for i in range(1, 5)
    ]
    concepts = [
        type(
            "Concept",
            (),
            {
                "label": f"新方案{i}",
                "identity_anchor": f"new anchor {i}",
                "prompt_en": realistic_prompt(f"new anchor {i}"),
            },
        )()
        for i in range(1, 5)
    ]

    with (
        patch("app.api.assets.store.get", return_value=source),
        patch("app.api.assets.store.list", return_value=old_group),
        patch(
            "app.api.assets.check_model",
            return_value={"ready": True, "missing_files": []},
        ),
        patch("app.api.assets.client.health", return_value=True),
        patch("app.api.assets.get_casting_service") as factory,
        patch("app.api.assets.store.update") as update,
        patch("app.api.assets.store.create") as create,
        patch("app.api.assets.queue.enqueue"),
        patch("app.api.assets.job_repo") as jobs,
    ):
        factory.return_value.generate.return_value = concepts
        create.side_effect = lambda **fields: {
            **source,
            "id": f"asset_new_{fields['candidate_index']}",
            **fields,
        }
        jobs.create.side_effect = lambda **kw: {
            "id": f"job_{kw['payload']['asset_id']}"
        }
        response = client.post(
            "/api/assets/p_recast/characters/asset_old_1/cast"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_group_id"] != "cast_old"
    assert [item["id"] for item in body["candidates"]] == [
        "asset_new_1",
        "asset_new_2",
        "asset_new_3",
        "asset_new_4",
    ]
    assert create.call_count == 4
    update.assert_not_called()


def test_select_endpoint_requires_completed_image_and_rejects_siblings():
    selected = {
        "id": "asset_c_2",
        "project_id": "p_select",
        "name": "苏遥",
        "name_en": "苏遥",
        "type": "character",
        "status": "completed",
        "prompt_cn": "方案2",
        "prompt_en": "polished commercial short-drama actor, anchor 2",
        "negative_prompt": "",
        "lock_en": "anchor 2",
        "model": "flux",
        "aspect": "portrait",
        "image_url": "/media/a2.png",
        "error": None,
        "created_at": "t",
        "candidate_group_id": "cast_1",
        "candidate_index": 2,
        "selection_status": "candidate",
    }
    siblings = [
        {**selected, "id": f"asset_c_{i}", "candidate_index": i}
        for i in range(1, 5)
    ]
    historical = {
        **selected,
        "id": "asset_old_selected",
        "candidate_group_id": "cast_old",
        "candidate_index": 1,
        "selection_status": "selected",
    }
    all_versions = [historical, *siblings]

    with patch("app.api.assets.store.get", return_value=selected):
        with patch("app.api.assets.store.list", return_value=all_versions):
            with patch("app.api.assets.store.update") as update:
                update.side_effect = lambda project_id, asset_id, **fields: {
                    **next(a for a in all_versions if a["id"] == asset_id),
                    **fields,
                }
                response = client.post(
                    "/api/assets/p_select/characters/asset_c_2/select"
                )

    assert response.status_code == 200
    statuses = {
        call.args[1]: call.kwargs["selection_status"]
        for call in update.call_args_list
    }
    assert statuses["asset_c_2"] == "selected"
    assert statuses["asset_old_selected"] == "rejected"
    assert list(statuses.values()).count("selected") == 1
    assert set(statuses.values()) == {"selected", "rejected"}


def test_select_endpoint_rejects_unfinished_candidate():
    candidate = {
        "id": "asset_c_1",
        "project_id": "p_select_bad",
        "type": "character",
        "status": "generating",
        "image_url": None,
        "candidate_group_id": "cast_2",
        "selection_status": "candidate",
    }
    with patch("app.api.assets.store.get", return_value=candidate):
        response = client.post(
            "/api/assets/p_select_bad/characters/asset_c_1/select"
        )
    assert response.status_code == 409
    assert response.json()["detail"] == "candidate_not_completed"
