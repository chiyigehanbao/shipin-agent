from pathlib import Path
from unittest.mock import MagicMock

from app.db.repositories.frames import FrameRepository
from app.db.repositories.scenes import SceneRepository
from app.services.storyboard_breakdown import StoryboardBreakdownService


def test_breakdown_assigns_all_line_ids(tmp_path: Path):
    db = tmp_path / "b.db"
    scenes = SceneRepository(db_path=db)
    frames = FrameRepository(db_path=db)
    scenes.replace_all(
        "p1",
        [
            {
                "id": "scene_1",
                "name": "咖啡馆",
                "lines": [
                    {
                        "id": "line_a",
                        "type": "dialogue",
                        "speaker": "甲",
                        "text": "一",
                        "emotion": "",
                    },
                    {
                        "id": "line_b",
                        "type": "narration",
                        "speaker": "旁白",
                        "text": "二",
                        "emotion": "",
                    },
                ],
            }
        ],
    )
    llm = MagicMock()
    llm.chat.return_value = (
        '{"frames":[{"scene_id":"scene_1","description":"特写","description_en":"A close-up",'
        '"prompt_en":"A grounded close-up of the table by the rainy cafe window, soft practical light, 50mm lens",'
        '"avoid":"text, watermark, duplicate hands, distorted face",'
        '"shot_type":"近景","duration":3,"line_ids":["line_a"]}]}',
        "ollama",
    )
    svc = StoryboardBreakdownService(llm=llm, scene_repo=scenes, frame_repo=frames)
    result = svc.run(project_id="p1", mode="replace_empty")
    assert result["frame_count"] >= 1
    all_ids = []
    for f in frames.list("p1"):
        all_ids.extend([x["id"] for x in f["lines"]])
        if f.get("description") == "特写":
            assert (f.get("prompt_en") or "").strip()
            assert (f.get("prompt_cn") or "").strip()
    assert "line_a" in all_ids and "line_b" in all_ids


def test_breakdown_retries_when_prompt_en_is_not_english(tmp_path: Path):
    db = tmp_path / "prompt.db"
    scenes = SceneRepository(db_path=db)
    frames = FrameRepository(db_path=db)
    scenes.replace_all(
        "p1",
        [{"id": "scene_1", "name": "咖啡馆", "lines": []}],
    )
    llm = MagicMock()
    llm.chat.side_effect = [
        (
            '{"frames":[{"scene_id":"scene_1","description":"特写",'
            '"prompt_en":"雨夜咖啡馆特写"}]}',
            "ollama",
        ),
        (
            '{"frames":[{"scene_id":"scene_1","description":"特写",'
            '"description_en":"A close-up",'
            '"prompt_en":"A close-up of a rain-streaked cafe window, motivated warm light, 50mm lens",'
            '"avoid":"text, watermark, malformed hands"}]}',
            "ollama",
        ),
    ]
    svc = StoryboardBreakdownService(llm=llm, scene_repo=scenes, frame_repo=frames)

    svc.run(project_id="p1", mode="replace_empty")

    assert llm.chat.call_count == 2
    assert "cafe window" in frames.list("p1")[0]["prompt_en"]


def test_breakdown_injects_lock_and_stores_motion(tmp_path: Path):
    db = tmp_path / "lock.db"
    scenes = SceneRepository(db_path=db)
    frames = FrameRepository(db_path=db)
    from app.db.repositories.assets import AssetRepository

    assets = AssetRepository(db_path=db)
    assets.create(
        project_id="p1",
        name="张三",
        type="character",
        prompt_cn="x",
        prompt_en="y",
        model="flux",
        lock_en="A man, 30s, short black hair, grey linen shirt.",
        status="pending",
    )
    a = assets.find_by_name_type("p1", "character", "张三")
    assets.update(
        "p1",
        a["id"],
        status="completed",
        image_url="/media/assets/p1/zhang.png",
    )
    scenes.replace_all(
        "p1",
        [
            {
                "id": "scene_1",
                "name": "咖啡馆",
                "location": "咖啡馆",
                "characters": ["张三"],
                "lines": [],
            }
        ],
    )
    llm = MagicMock()
    llm.chat.return_value = (
        '{"frames":[{"scene_id":"scene_1","description":"特写",'
        '"description_en":"A close-up",'
        '"prompt_en":"A close-up of a rain-streaked cafe window, motivated warm light, 50mm lens",'
        '"motion_prompt_en":"He turns toward the door. Slow push-in. About 5s. Keep identity from the first frame.",'
        '"avoid":"text, watermark, malformed hands","shot_type":"近景","duration":3,"line_ids":[]}]}',
        "ollama",
    )
    svc = StoryboardBreakdownService(
        llm=llm, scene_repo=scenes, frame_repo=frames, asset_repo=assets
    )
    svc.run(project_id="p1", mode="replace_empty")
    fr = frames.list("p1")[0]
    assert "short black hair, grey linen shirt" in fr["prompt_en"]
    assert fr["motion_prompt_en"].startswith("He turns")
    assert fr["motion_prompt_en"] != fr["prompt_en"]


def test_breakdown_pads_missing_scenes_after_retry(tmp_path: Path):
    db = tmp_path / "pad.db"
    scenes = SceneRepository(db_path=db)
    frames = FrameRepository(db_path=db)
    scenes.replace_all(
        "p1",
        [
            {"id": "scene_a", "name": "场A", "lines": []},
            {"id": "scene_b", "name": "场B", "lines": []},
            {"id": "scene_c", "name": "场C", "lines": []},
        ],
    )
    only_a = (
        '{"frames":[{"scene_id":"scene_a","description":"A",'
        '"description_en":"Shot A",'
        '"prompt_en":"A medium shot of scene A with motivated warm light, 50mm lens, mild grain",'
        '"motion_prompt_en":"Subject turns slightly. Camera locked-off. About 5s. Keep identity from the first frame.",'
        '"avoid":"text, watermark","shot_type":"中景","duration":3,"line_ids":[]}]}'
    )
    llm = MagicMock()
    llm.chat.side_effect = [(only_a, "ollama"), (only_a, "ollama")]
    svc = StoryboardBreakdownService(llm=llm, scene_repo=scenes, frame_repo=frames)
    result = svc.run(project_id="p1", mode="replace_empty")
    assert result["created"] >= 3
    covered = {f["scene_id"] for f in frames.list("p1")}
    assert covered == {"scene_a", "scene_b", "scene_c"}
    assert llm.chat.call_count == 2
    retry_user = llm.chat.call_args_list[1][0][0][-1]["content"]
    assert "scene_b" in retry_user and "scene_c" in retry_user


def test_breakdown_blocks_unready_characters(tmp_path: Path):
    from app.services.storyboard_breakdown import StoryboardBreakdownError

    db = tmp_path / "gate.db"
    scenes = SceneRepository(db_path=db)
    frames = FrameRepository(db_path=db)
    from app.db.repositories.assets import AssetRepository

    assets = AssetRepository(db_path=db)
    assets.create(
        project_id="p1",
        name="苏遥",
        type="character",
        prompt_cn="x",
        prompt_en="y",
        model="flux",
        lock_en="",
        status="pending",
    )
    scenes.replace_all(
        "p1",
        [
            {
                "id": "scene_1",
                "name": "天台",
                "characters": ["苏遥"],
                "lines": [],
            }
        ],
    )
    llm = MagicMock()
    svc = StoryboardBreakdownService(
        llm=llm, scene_repo=scenes, frame_repo=frames, asset_repo=assets
    )
    try:
        svc.run(project_id="p1", mode="replace_empty")
        assert False, "expected StoryboardBreakdownError"
    except StoryboardBreakdownError as e:
        assert "characters_not_ready" in str(e)
        assert "苏遥" in str(e)
    llm.chat.assert_not_called()


