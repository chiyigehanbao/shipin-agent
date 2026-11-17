from fastapi.testclient import TestClient

from app.main import app
from app.core.settings import settings


def test_readiness_endpoint_reports_missing(monkeypatch, tmp_path):
    models = tmp_path / "comfyui" / "models"
    models.mkdir(parents=True)
    monkeypatch.setattr(settings, "modelhub_root", tmp_path)
    monkeypatch.setattr("app.api.models.client.health", lambda: False)

    client = TestClient(app)
    res = client.get("/api/models/readiness")
    assert res.status_code == 200
    body = res.json()
    assert body["models"]["flux"]["ready"] is False
    assert body["face_identity"]["ready"] is False
    assert body["face_identity"]["reason"] == "face_model_files_missing"
    assert "comfyui_online" in body


def test_generate_rejects_unready_model(monkeypatch, tmp_path):
    models = tmp_path / "comfyui" / "models"
    models.mkdir(parents=True)
    monkeypatch.setattr(settings, "modelhub_root", tmp_path)

    client = TestClient(app)
    res = client.post(
        "/api/assets/proj_test/generate",
        json={
            "name": "t",
            "type": "character",
            "prompt_cn": "a",
            "prompt_en": "a",
            "model": "flux",
        },
    )
    assert res.status_code == 400
    detail = res.json()["detail"].lower()
    assert "not ready" in detail or "missing" in detail
