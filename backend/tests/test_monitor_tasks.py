from fastapi.testclient import TestClient
from app.main import app
from app.services.runtime import job_repo

client = TestClient(app)


def _make_job(project_id: str = "p_mon") -> str:
    job = job_repo.create(
        type="script_expand",
        project_id=project_id,
        title="测试任务",
        payload={"text": "x"},
    )
    return job["id"]


def test_cancel_queued_task():
    jid = _make_job()
    r = client.post(f"/api/monitor/tasks/{jid}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_pause_and_resume_queued_task():
    jid = _make_job()
    r_pause = client.post(f"/api/monitor/tasks/{jid}/pause")
    assert r_pause.status_code == 200
    assert r_pause.json()["status"] == "paused"

    r_resume = client.post(f"/api/monitor/tasks/{jid}/resume")
    assert r_resume.status_code == 200
    assert r_resume.json()["status"] == "queued"


def test_pause_missing_task_404():
    r = client.post("/api/monitor/tasks/does_not_exist/pause")
    assert r.status_code == 404


def test_resume_non_paused_task_400():
    jid = _make_job()
    r = client.post(f"/api/monitor/tasks/{jid}/resume")
    assert r.status_code == 400
