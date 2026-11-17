from pathlib import Path

from fastapi.testclient import TestClient


def test_start_render_returns_job_id(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MODELHUB_ROOT", str(tmp_path))
    # Use isolated sqlite if settings support — rely on default test client
    from app.main import app

    client = TestClient(app)
    # project may 404; create via projects API if available
    r = client.post(
        "/api/projects",
        json={"name": "t", "type": "短剧", "description": ""},
    )
    if r.status_code >= 400:
        # fallback: still call render; job create does not require project existence today
        pid = "proj_test"
    else:
        pid = r.json()["id"]
    resp = client.post(
        f"/api/render/{pid}/render",
        json={"episode_id": "__all__", "engine": "edge", "voice_enabled": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("job_id") or body.get("task_id")
