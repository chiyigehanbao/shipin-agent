from pathlib import Path

from fastapi.testclient import TestClient

from app.db.connection import connect
from app.db.repositories.projects import ProjectRepository
from app.db.schema import migrate
from app.main import app


def test_create_survives_reconnect(tmp_path: Path):
    db = tmp_path / "t.db"
    migrate(connect(db))
    repo = ProjectRepository(db)
    created = repo.create(name="留存测试", type="drama", description="d", style="s")
    pid = created["id"]
    again = ProjectRepository(db)
    got = again.get(pid)
    assert got is not None
    assert got["name"] == "留存测试"


def test_projects_api_create_and_get(tmp_path: Path):
    db = tmp_path / "api.db"
    from app.api import projects as projects_api

    projects_api._repo = ProjectRepository(db)
    client = TestClient(app)
    r = client.post(
        "/api/projects",
        json={"name": "API项目", "type": "drama", "description": "x", "style": "y"},
    )
    assert r.status_code == 200
    pid = r.json()["id"]
    r2 = client.get(f"/api/projects/{pid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "API项目"


def test_delete_cascades_to_child_tables(tmp_path: Path):
    db = tmp_path / "cascade.db"
    migrate(connect(db))
    repo = ProjectRepository(db)
    created = repo.create(name="级联删除", type="drama")
    pid = created["id"]

    with connect(db) as conn:
        inserts = {
            "scenes": "INSERT INTO scenes (id, project_id, created_at, updated_at) VALUES (?, ?, 't', 't')",
            "assets": "INSERT INTO assets (id, project_id, type, status, created_at, updated_at) VALUES (?, ?, 'character', 'pending', 't', 't')",
            "storyboard_frames": "INSERT INTO storyboard_frames (id, project_id, status, created_at, updated_at) VALUES (?, ?, 'pending', 't', 't')",
            "jobs": "INSERT INTO jobs (id, project_id, type, status, created_at) VALUES (?, ?, 'asset', 'queued', 't')",
            "renders": "INSERT INTO renders (id, project_id, status, created_at) VALUES (?, ?, 'completed', 't')",
        }
        for table, sql in inserts.items():
            conn.execute(sql, (f"{table}_1", pid))
        conn.commit()

    repo.delete(pid)
    assert repo.get(pid) is None
    with connect(db) as conn:
        for table in ("scenes", "assets", "storyboard_frames", "jobs", "renders"):
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            assert row["n"] == 0, f"orphan rows left in {table}"


def test_delete_missing_project_raises(tmp_path: Path):
    db = tmp_path / "missing.db"
    migrate(connect(db))
    repo = ProjectRepository(db)
    try:
        repo.delete("nope")
    except KeyError:
        return
    raise AssertionError("expected KeyError for missing project")
