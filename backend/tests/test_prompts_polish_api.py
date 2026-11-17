from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.services.cinematic_polish import PolishError

client = TestClient(app)


def test_polish_ok():
    fake = {
        "interpretation_cn": "理解",
        "prompt_en": "frame",
        "avoid": "hdr look",
        "prompt_cn": "画面",
        "provider": "ollama",
        "pack_version": "cinematic-v1",
    }
    with patch("app.api.prompts.get_polish_service") as g:
        g.return_value.polish.return_value = fake
        r = client.post(
            "/api/prompts/polish",
            json={
                "stage": "asset",
                "project_id": "p1",
                "input": {"text_cn": "角色", "text_en": "", "context": {"type": "character"}},
                "options": {"director": None, "return_interpretation": True},
            },
        )
    assert r.status_code == 200
    assert r.json()["prompt_en"] == "frame"
    assert r.json()["provider"] == "ollama"


def test_polish_bad_stage():
    r = client.post(
        "/api/prompts/polish",
        json={"stage": "nope", "project_id": "p1", "input": {"text_cn": "x"}},
    )
    assert r.status_code == 400


def test_polish_service_error_returns_502():
    with patch("app.api.prompts.get_polish_service") as g:
        g.return_value.polish.side_effect = PolishError("invalid polish output")
        r = client.post(
            "/api/prompts/polish",
            json={
                "stage": "asset",
                "project_id": "p1",
                "input": {"text_cn": "角色"},
            },
        )
    assert r.status_code == 502


def test_polish_character_lock_stage_ok():
    fake = {
        "interpretation_cn": "",
        "prompt_en": "portrait",
        "avoid": "blurry",
        "prompt_cn": "",
        "lock_en": "LOCK",
        "motion_prompt_en": "",
        "provider": "ollama",
        "pack_version": "character-lock-v1",
    }
    with patch("app.api.prompts.get_polish_service") as g:
        g.return_value.polish.return_value = fake
        r = client.post(
            "/api/prompts/polish",
            json={
                "stage": "character_lock",
                "project_id": "p1",
                "input": {"text_cn": "角色"},
            },
        )
    assert r.status_code == 200
    assert r.json()["lock_en"] == "LOCK"

