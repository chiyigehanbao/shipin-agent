from pathlib import Path

from app.db.repositories.scenes import SceneRepository


def test_replace_and_update_scene(tmp_path: Path):
    repo = SceneRepository(tmp_path / "s.db")
    scenes = repo.replace_all(
        "proj_1",
        [
            {
                "name": "场1",
                "location": "咖啡馆",
                "time": "下午",
                "characters": ["张三"],
                "props": ["杯"],
                "description": "描述",
                "dialogue_count": 2,
            }
        ],
    )
    assert len(scenes) == 1
    sid = scenes[0]["id"]
    updated = repo.update(
        "proj_1",
        sid,
        prompt_en="cinematic frame",
        negative_prompt="hdr look",
        interpretation_cn="理解",
    )
    assert updated["prompt_en"] == "cinematic frame"
    assert updated["negative_prompt"] == "hdr look"
    listed = repo.list_by_project("proj_1")
    assert listed[0]["prompt_en"] == "cinematic frame"


def test_replace_all_persists_lines(tmp_path: Path):
    repo = SceneRepository(db_path=tmp_path / "s.db")
    out = repo.replace_all(
        "p1",
        [
            {
                "name": "S",
                "lines": [
                    {
                        "id": "line_1",
                        "type": "dialogue",
                        "speaker": "A",
                        "text": "hi",
                        "emotion": "",
                    }
                ],
            }
        ],
    )
    assert out[0]["lines"][0]["text"] == "hi"
    got = repo.get("p1", out[0]["id"])
    assert got["lines"][0]["id"] == "line_1"
    assert got["dialogue_count"] == 1


def test_scene_look_states_round_trip(tmp_path: Path):
    repo = SceneRepository(tmp_path / "scene.db")
    scene = repo.replace_all("p1", [{"name": "雨巷"}])[0]
    assert scene["look_states"] == {}
    updated = repo.update(
        "p1",
        scene["id"],
        look_states={
            "asset_c_1": {
                "wardrobe": "dark wool coat",
                "wetness": "rain-soaked hair and shoulders",
            }
        },
    )
    assert updated["look_states"]["asset_c_1"]["wardrobe"] == "dark wool coat"
