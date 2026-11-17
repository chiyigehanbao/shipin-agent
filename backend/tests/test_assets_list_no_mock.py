from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)


def test_list_assets_empty_without_mock_seeds():
    with patch("app.api.assets.store.list", return_value=[]):
        r = client.get("/api/assets/proj_empty/assets")
    assert r.status_code == 200
    assert r.json() == []
