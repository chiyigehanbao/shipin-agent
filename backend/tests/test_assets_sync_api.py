from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)


def test_sync_from_script_400_without_scenes():
    with patch("app.api.assets.ProjectRepository") as PR:
        with patch("app.api.assets.SceneRepository") as SR:
            PR.return_value.get.return_value = {"id": "p", "style": "古风"}
            SR.return_value.list_by_project.return_value = []
            r = client.post("/api/assets/p/sync-from-script", json={})
    assert r.status_code == 400
    assert "剧本" in str(r.json().get("detail"))
