from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)

PAYLOAD = {
    "name": "张三",
    "type": "character",
    "prompt_cn": "年轻男子",
    "prompt_en": "young man",
    "model": "flux",
}


def test_generate_rejects_when_comfy_unhealthy():
    with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.assets.client") as mock_client:
            mock_client.health.return_value = False
            with patch("app.api.assets.queue.enqueue") as enq:
                r = client.post("/api/assets/p1/generate", json=PAYLOAD)
    assert r.status_code == 503
    assert "comfyui_unavailable" in str(r.json().get("detail"))
    enq.assert_not_called()


def test_generate_enqueues_when_comfy_healthy():
    with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.assets.client") as mock_client:
            mock_client.health.return_value = True
            with patch("app.api.assets.queue.enqueue") as enq:
                with patch("app.api.assets.store.create") as create:
                    create.return_value = {
                        **PAYLOAD,
                        "id": "asset_c_1",
                        "status": "generating",
                        "name_en": "张三",
                        "created_at": "t",
                        "image_url": None,
                        "error": None,
                        "negative_prompt": "",
                    }
                    with patch("app.api.assets.job_repo") as jobs:
                        jobs.create.return_value = {"id": "job_1"}
                        r = client.post("/api/assets/p1/generate", json=PAYLOAD)
    assert r.status_code == 200
    enq.assert_called_once()


def test_generate_with_asset_id_updates_existing():
    existing = {
        **PAYLOAD,
        "id": "asset_c_1",
        "status": "failed",
        "name_en": "张三",
        "created_at": "t",
        "image_url": None,
        "error": "old",
        "negative_prompt": "",
        "lock_en": "",
    }
    updated = {**existing, "status": "generating", "error": None, "prompt_en": "new man"}
    with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.assets.client") as mock_client:
            mock_client.health.return_value = True
            with patch("app.api.assets.queue.enqueue") as enq:
                with patch("app.api.assets.store.create") as create:
                    with patch("app.api.assets.store.get", return_value=existing):
                        with patch("app.api.assets.store.update", return_value=updated) as upd:
                            with patch("app.api.assets.job_repo") as jobs:
                                jobs.create.return_value = {"id": "job_1"}
                                r = client.post(
                                    "/api/assets/p1/generate",
                                    json={**PAYLOAD, "asset_id": "asset_c_1", "prompt_en": "new man"},
                                )
    assert r.status_code == 200
    assert r.json()["id"] == "asset_c_1"
    create.assert_not_called()
    upd.assert_called_once()
    enq.assert_called_once_with("p1", "asset_c_1")


def test_generate_with_asset_id_rejects_when_busy():
    busy = {**PAYLOAD, "id": "asset_c_1", "status": "generating", "name_en": "张三", "created_at": "t"}
    with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.assets.client") as mock_client:
            mock_client.health.return_value = True
            with patch("app.api.assets.queue.enqueue") as enq:
                with patch("app.api.assets.store.get", return_value=busy):
                    with patch("app.api.assets.store.create") as create:
                        r = client.post(
                            "/api/assets/p1/generate",
                            json={**PAYLOAD, "asset_id": "asset_c_1"},
                        )
    assert r.status_code == 409
    create.assert_not_called()
    enq.assert_not_called()
