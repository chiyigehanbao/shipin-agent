import json
from pathlib import Path

from app.db.connection import connect
from app.db.repositories.jobs import JobRepository
from app.db.schema import migrate


def test_create_and_list_active(tmp_path: Path):
    db = tmp_path / "t.db"
    migrate(connect(db))
    repo = JobRepository(db)
    j = repo.create(
        type="script_expand",
        project_id="p1",
        title="剧本扩写",
        payload={"text": "hi"},
        link_path="/workbench/p1/script",
    )
    assert j["status"] == "queued"
    assert j["id"]
    active = repo.list_active(limit=10)
    assert len(active) == 1
    assert active[0]["id"] == j["id"]
    assert active[0]["payload"]["text"] == "hi"


def test_fail_stale_marks_queued_and_running(tmp_path: Path):
    db = tmp_path / "t.db"
    migrate(connect(db))
    repo = JobRepository(db)
    a = repo.create(type="script_expand", project_id="p1", title="a", payload={})
    b = repo.create(type="script_expand", project_id="p1", title="b", payload={})
    repo.update(b["id"], status="running", progress=10)
    n = repo.fail_stale(error="server_restarted")
    assert n == 2
    assert repo.get(a["id"])["status"] == "failed"
    assert repo.get(b["id"])["error"] == "server_restarted"
