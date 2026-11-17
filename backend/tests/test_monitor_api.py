from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FAKE = {
    "ts": "2026-08-11T22:00:00",
    "host": {"cpu_percent": 1, "memory_percent": 2, "disk_percent": 3},
    "gpu": {
        "available": True,
        "name": "X",
        "temperature_c": 62,
        "utilization_percent": 78,
        "memory_used_mb": 1,
        "memory_total_mb": 2,
        "error": None,
    },
    "services": {
        "comfyui": {"online": True, "queue": 0},
        "ollama": {"online": False, "model": "q"},
    },
    "tasks": {"badge_count": 0, "generating": [], "failed_recent": []},
}


def test_snapshot_endpoint():
    with patch("app.api.monitor.build_snapshot", return_value=FAKE):
        r = client.get("/api/monitor/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["gpu"]["temperature_c"] == 62
    assert "tasks" in body


def test_pause_missing_task_404():
    # 任务不存在 -> 404（替代旧 501「未实现」占位）
    r = client.post("/api/monitor/tasks/t1/pause")
    assert r.status_code == 404
