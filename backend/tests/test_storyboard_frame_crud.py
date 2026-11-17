from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_create_frame_appends_and_counts():
    r = client.post("/api/storyboard/p_crud/frames", json={"description": "新增分镜", "character": "苏晚"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["character"] == "苏晚"
    assert body["number"] >= 1

    # 编号递增
    r2 = client.post("/api/storyboard/p_crud/frames", json={"description": "第二帧"})
    assert r2.status_code == 200
    assert r2.json()["number"] > body["number"]


def test_duplicate_via_create_keeps_fields():
    r = client.post(
        "/api/storyboard/p_crud2/frames",
        json={"description": "源帧", "scene": "废弃车站", "character": "陈默"},
    )
    fid = r.json()["id"]
    assert r.json()["scene"] == "废弃车站"


def test_delete_frame_removes_single_frame():
    created = client.post("/api/storyboard/p_crud3/frames", json={"description": "待删"})
    fid = created.json()["id"]
    r = client.delete(f"/api/storyboard/p_crud3/frames/{fid}")
    assert r.status_code == 200

    # 删除后列表不再包含该帧
    frames = client.get("/api/storyboard/p_crud3/frames").json()
    assert all(f["id"] != fid for f in frames)


def test_delete_missing_frame_still_returns_success():
    r = client.delete("/api/storyboard/p_crud4/frames/does_not_exist")
    assert r.status_code == 200
