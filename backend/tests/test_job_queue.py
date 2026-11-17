import time
from pathlib import Path

from app.db.connection import connect
from app.db.repositories.jobs import JobRepository
from app.db.schema import migrate
from app.services.job_queue import JobQueue


def test_worker_runs_handler_and_completes(tmp_path: Path):
    db = tmp_path / "t.db"
    migrate(connect(db))
    repo = JobRepository(db)
    calls = []

    def handler(job):
        calls.append(job["id"])
        return {"ok": True}

    q = JobQueue(repo=repo, dispatch=handler)
    q.start()
    job = repo.create(type="script_expand", project_id="p1", title="t", payload={})
    q.enqueue(job["id"])
    for _ in range(50):
        j = repo.get(job["id"])
        if j and j["status"] == "completed":
            break
        time.sleep(0.05)
    q.stop()
    assert repo.get(job["id"])["status"] == "completed"
    assert calls == [job["id"]]


def test_handler_error_marks_failed(tmp_path: Path):
    db = tmp_path / "t.db"
    migrate(connect(db))
    repo = JobRepository(db)

    def handler(job):
        raise RuntimeError("boom")

    q = JobQueue(repo=repo, dispatch=handler)
    q.start()
    job = repo.create(type="script_expand", project_id="p1", title="t", payload={})
    q.enqueue(job["id"])
    for _ in range(50):
        j = repo.get(job["id"])
        if j and j["status"] == "failed":
            break
        time.sleep(0.05)
    q.stop()
    assert "boom" in (repo.get(job["id"])["error"] or "")
