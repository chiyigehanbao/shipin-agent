from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import scripts as scripts_api
from app.db.repositories.projects import ProjectRepository
from app.db.repositories.scenes import SceneRepository
from app.main import app


def test_expand_persists_scenes(tmp_path):
    db = tmp_path / "e.db"
    scripts_api._project_repo = ProjectRepository(db)
    scripts_api._scene_repo = SceneRepository(db)
    project = scripts_api._project_repo.create(name="P", type="drama")
    client = TestClient(app)

    fake_scenes = [
        {
            "name": "场A",
            "location": "咖啡",
            "time": "午",
            "characters": ["张"],
            "props": ["杯"],
            "description": "描述",
            "dialogue_count": 2,
            "narration_count": 0,
        }
    ]
    with patch("app.api.scripts._expand_service") as g:
        g.return_value.expand.return_value = fake_scenes
        r = client.post(
            "/api/scripts/expand",
            json={"project_id": project["id"], "text": "一个关于咖啡的故事", "style": "都市"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["scene_count"] == 1
    assert body["scenes"][0]["name"] == "场A"
    listed = scripts_api._scene_repo.list_by_project(project["id"])
    assert len(listed) == 1


def test_expand_missing_project_404(tmp_path):
    db = tmp_path / "e2.db"
    scripts_api._project_repo = ProjectRepository(db)
    scripts_api._scene_repo = SceneRepository(db)
    client = TestClient(app)
    r = client.post(
        "/api/scripts/expand",
        json={"project_id": "missing", "text": "x"},
    )
    assert r.status_code == 404
