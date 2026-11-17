from fastapi.testclient import TestClient
from app.db.repositories.scenes import SceneRepository
from app.main import app

client = TestClient(app)


def test_complete_project_auto_ingests():
    r = client.post("/api/projects", json={"name": "RAG测试", "type": "短剧", "description": ""})
    assert r.status_code == 200
    pid = r.json()["id"]
    SceneRepository().replace_all(
        pid,
        [{"name": "雨夜追车", "prompt_en": "wide shot, rain car chase at night", "lines": []}],
    )

    cr = client.post(f"/api/projects/{pid}/complete")
    assert cr.status_code == 200
    body = cr.json()
    assert body["status"] == "completed"
    assert body["ingested"]["scene"] >= 1
    assert body["ingested"]["total"] >= 1


def test_complete_missing_project_404():
    r = client.post("/api/projects/p_nope/complete")
    assert r.status_code == 404
