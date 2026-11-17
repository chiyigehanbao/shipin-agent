from pathlib import Path

from app.db.connection import connect
from app.db.schema import migrate


def test_migrate_creates_tables(tmp_path: Path):
    db = tmp_path / "t.db"
    conn = connect(db)
    migrate(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "projects" in tables
    assert "scenes" in tables
    assert "assets" in tables
    assert "storyboard_frames" in tables
    assert "renders" in tables
    assert "schema_migrations" in tables
    migrate(conn)  # idempotent
    ids = {
        row[0]
        for row in conn.execute("SELECT id FROM schema_migrations").fetchall()
    }
    assert "001_init" in ids
    assert "004_render_tts" in ids
    cols_scenes = {
        r[1] for r in conn.execute("PRAGMA table_info(scenes)").fetchall()
    }
    assert "lines_json" in cols_scenes
    cols_frames = {
        r[1] for r in conn.execute("PRAGMA table_info(storyboard_frames)").fetchall()
    }
    assert "lines_json" in cols_frames
    assert "scene_id" in cols_frames
    conn.close()


def test_storyboard_render_schema(tmp_path: Path):
    conn = connect(tmp_path / "render-schema.db")
    migrate(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "storyboard_render_requests" in tables
    assert "storyboard_render_attempts" in tables
    scene_cols = {r[1] for r in conn.execute("PRAGMA table_info(scenes)")}
    asset_cols = {r[1] for r in conn.execute("PRAGMA table_info(assets)")}
    frame_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(storyboard_frames)")
    }
    attempt_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(storyboard_render_attempts)")
    }
    assert "look_states_json" in scene_cols
    assert "identity_json" in asset_cols
    assert "accepted_render_attempt_id" in frame_cols
    assert "identity_evaluation_json" in attempt_cols
    conn.close()
