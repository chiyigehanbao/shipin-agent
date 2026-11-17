from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)


def test_generate_accepts_negative_prompt():
    with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.assets.client") as mock_client:
            mock_client.health.return_value = True
            with patch("app.api.assets.queue.enqueue"):
                r = client.post(
                    "/api/assets/p1/generate",
                    json={
                        "name": "A",
                        "type": "character",
                        "prompt_cn": "猫",
                        "prompt_en": "a cat",
                        "negative_prompt": "hdr look",
                        "model": "flux",
                    },
                )
    assert r.status_code == 200
    assert r.json().get("negative_prompt") == "hdr look"
