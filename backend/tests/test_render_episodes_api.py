from fastapi.testclient import TestClient
from app.db.repositories.renders import RenderRepository
from app.db.repositories.scenes import SceneRepository
from app.main import app

client = TestClient(app)


def test_episodes_reflects_per_scene_render():
    pid = "p_episodes"
    # 隔离该 test 项目：重建一个场景
    scenes = SceneRepository().replace_all(
        pid, [{"name": "屋顶对峙", "location": "天台", "lines": []}]
    )
    scene = scenes[0]
    # 为该场景造一条已完成 render
    RenderRepository().create(
        project_id=pid,
        scene_id=scene["id"],
        status="completed",
        output_url="/media/renders/p_episodes/abc.mp4",
        duration_sec=75,
    )

    r = client.get(f"/api/render/{pid}/episodes")
    assert r.status_code == 200
    items = r.json()
    scene_ep = next((e for e in items if e["id"] == scene["id"]), None)
    assert scene_ep is not None
    assert scene_ep["status"] == "completed"
    assert scene_ep["video_url"] == "/media/renders/p_episodes/abc.mp4"
    assert scene_ep["duration"] == "01:15"


def test_episodes_unrendered_scene_is_pending():
    pid = "p_episodes_pending"
    scenes = SceneRepository().replace_all(
        pid, [{"name": "未合成的场景", "location": "走廊", "lines": []}]
    )
    scene = scenes[0]
    r = client.get(f"/api/render/{pid}/episodes")
    scene_ep = next((e for e in r.json() if e["id"] == scene["id"]), None)
    assert scene_ep["status"] == "pending"
    assert scene_ep["video_url"] is None
