from pathlib import Path

from app.db.repositories.frames import FrameRepository


def test_frame_lines_and_scene_id(tmp_path: Path):
    repo = FrameRepository(db_path=tmp_path / "f.db")
    f = repo.create(
        "p1",
        scene_id="scene_x",
        description="shot",
        lines=[
            {
                "id": "line_1",
                "type": "dialogue",
                "speaker": "A",
                "text": "hi",
                "emotion": "",
            }
        ],
    )
    assert f["scene_id"] == "scene_x"
    assert f["lines"][0]["text"] == "hi"
    got = repo.get("p1", f["id"])
    assert got["lines"][0]["id"] == "line_1"
