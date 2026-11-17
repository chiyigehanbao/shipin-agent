import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.connection import connect
from app.db.repositories.jobs import JobRepository
from app.db.schema import migrate
from app.main import app
from app.services.job_queue import JobQueue


def test_create_job_lists_active(tmp_path: Path):
    db = tmp_path / "jobs_api.db"
    migrate(connect(db))
    repo = JobRepository(db)

    def fake_dispatch(job):
        return {"scene_count": 1}

    q = JobQueue(repo=repo, dispatch=fake_dispatch)
    q.start()
    try:
        client = TestClient(app, raise_server_exceptions=True)
        with patch("app.api.jobs.job_repo", repo), patch("app.api.jobs.job_queue", q):
            r = client.post(
                "/api/jobs",
                json={
                    "type": "script_expand",
                    "project_id": "p1",
                    "payload": {"text": "hello"},
                },
            )
            assert r.status_code == 200
            jid = r.json()["id"]

            for _ in range(50):
                got = repo.get(jid)
                if got and got["status"] == "completed":
                    break
                time.sleep(0.05)
            assert repo.get(jid)["status"] == "completed"

            r2 = client.get("/api/jobs?status=active")
            assert r2.status_code == 200
            assert isinstance(r2.json(), list)
    finally:
        q.stop()
