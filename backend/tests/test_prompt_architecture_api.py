from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.repositories.compiled_prompts import CompiledPromptRepository
from app.main import app
from app.services.h3_validator import I2VA_ALIGNMENT


client = TestClient(app)

VALID_I2VA = f"""{I2VA_ALIGNMENT}

integrated_multimodal_description: [Shot 1] Live-action, cinematic, the subject shown in <Picture 1> remains in place while the camera slowly pushes in.

overall_soundscape: Quiet room tone and soft fabric movement.

non_diegetic_music: N/A"""


def test_visual_bible_get_and_update():
    got = client.get("/api/prompts/visual-bible/p_api")
    assert got.status_code == 200
    body = got.json()
    assert "commercial short-drama" in body["casting_aesthetic"]
    body["cinematography"] = ["restrained handheld"]
    saved = client.put("/api/prompts/visual-bible/p_api", json=body)
    assert saved.status_code == 200
    assert saved.json()["cinematography"] == ["restrained handheld"]


def test_h3_compile_endpoint_returns_artifact():
    artifact = {
        "id": "cp_api",
        "project_id": "p1",
        "source_type": "frame",
        "source_id": "f1",
        "target_model": "minimax-h3",
        "mode": "i2va",
        "source_hash": "abc",
        "guide_version": "minimax-h3@d21241f",
        "content": VALID_I2VA,
        "validation_json": {"valid": True, "issues": []},
        "provider": "ollama",
        "status": "draft",
        "is_user_edited": False,
        "created_at": "2026-08-28 00:00:00",
        "updated_at": "2026-08-28 00:00:00",
        "stale": False,
    }
    with patch("app.api.prompt_architecture.get_h3_compiler") as factory:
        factory.return_value.compile_frame.return_value = artifact
        response = client.post(
            "/api/prompts/h3/compile",
            json={
                "project_id": "p1",
                "source_type": "frame",
                "source_id": "f1",
                "mode": "i2va",
                "duration_sec": 5.17,
            },
        )
    assert response.status_code == 200
    assert response.json()["id"] == "cp_api"


def test_h3_edit_revalidates_and_can_lock():
    repo = CompiledPromptRepository()
    row = repo.create(
        project_id="p1",
        source_type="frame",
        source_id="f1",
        target_model="minimax-h3",
        mode="i2va",
        source_hash="abc",
        guide_version="minimax-h3@d21241f",
        content=VALID_I2VA,
        validation={"valid": True, "issues": []},
        provider="ollama",
    )
    response = client.put(
        f"/api/prompts/h3/{row['id']}",
        json={"content": VALID_I2VA, "status": "locked", "duration_sec": 5.17},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "locked"
    assert body["is_user_edited"] is True
    assert body["validation_json"]["valid"] is True
