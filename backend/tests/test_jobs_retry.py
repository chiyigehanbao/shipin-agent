from fastapi.testclient import TestClient
from app.main import app
from app.services.runtime import job_repo

client = TestClient(app)


def _make_failed(project_id: str = "p_jr", job_type: str = "script_expand") -> str:
    j = job_repo.create(type=job_type, project_id=project_id, title="测试", payload={"text": "x"})
    job_repo.update(j["id"], status="failed", error="boom")
    return j["id"]


def test_retry_re_enqueues_failed_llm_job():
    jid = _make_failed()
    r = client.post(f"/api/jobs/{jid}/retry")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert body["error"] is None


def test_retry_non_failed_returns_400():
    j = job_repo.create(type="script_expand", project_id="p_jr2", title="t", payload={})
    r = client.post(f"/api/jobs/{j['id']}/retry")
    assert r.status_code == 400


def test_retry_asset_generate_returns_400():
    jid = _make_failed(project_id="p_jr3", job_type="asset_generate")
    r = client.post(f"/api/jobs/{jid}/retry")
    assert r.status_code == 400


def test_retry_missing_job_404():
    r = client.post("/api/jobs/nope/retry")
    assert r.status_code == 404
