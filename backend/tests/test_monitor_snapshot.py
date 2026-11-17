from app.services.asset_store import AssetStore
from app.services import monitor_snapshot as ms


def test_snapshot_badge_counts(tmp_path, monkeypatch):
    ms.clear_probe_cache()
    store = AssetStore(tmp_path / "t.db")
    a = store.create(
        project_id="p1",
        name="A",
        type="character",
        prompt_cn="x",
        prompt_en="",
        model="flux",
    )
    store.update("p1", a["id"], status="failed", error="boom")
    store.create(
        project_id="p1",
        name="B",
        type="scene",
        prompt_cn="y",
        prompt_en="",
        model="flux",
    )
    monkeypatch.setattr(ms, "store", store)

    class Q:
        def pending_count(self):
            return 0

    class FakeJobs:
        def list_active(self, limit=50):
            return [
                {
                    "id": "job_1",
                    "project_id": "p1",
                    "title": "扩写",
                    "type": "script_expand",
                    "status": "running",
                    "error": None,
                    "created_at": "2026-08-12",
                    "link_path": "/x",
                    "progress": 10,
                },
                {
                    "id": "job_2",
                    "project_id": "p1",
                    "title": "成片",
                    "type": "render_compose",
                    "status": "queued",
                    "error": None,
                    "created_at": "2026-08-12",
                    "link_path": "/y",
                    "progress": 0,
                },
            ][:limit]

        def list_recent_failed(self, limit=20):
            return [
                {
                    "id": "job_f",
                    "project_id": "p1",
                    "title": "失败",
                    "type": "script_expand",
                    "status": "failed",
                    "error": "boom",
                    "created_at": "2026-08-12",
                    "link_path": "/z",
                    "progress": 0,
                }
            ][:limit]

    monkeypatch.setattr(ms, "queue", Q())
    monkeypatch.setattr(ms, "job_repo", FakeJobs())
    monkeypatch.setattr(
        ms,
        "read_host_stats",
        lambda: {"cpu_percent": 1, "memory_percent": 2, "disk_percent": 3},
    )
    monkeypatch.setattr(
        ms,
        "read_gpu_stats",
        lambda: {
            "available": True,
            "temperature_c": 50,
            "utilization_percent": 10,
            "name": "X",
            "memory_used_mb": 1,
            "memory_total_mb": 2,
            "error": None,
        },
    )
    monkeypatch.setattr(
        ms,
        "effective_llm_kwargs",
        lambda: {"ollama_base_url": "", "ollama_model": "m"},
    )
    snap = ms.build_snapshot(comfy_online=True)
    assert snap["tasks"]["badge_count"] == 2
    assert len(snap["tasks"]["failed_recent"]) == 1
    assert snap["gpu"]["temperature_c"] == 50


def test_probe_cache_skips_second_gpu_read(monkeypatch):
    ms.clear_probe_cache()
    calls = {"gpu": 0}

    def fake_gpu():
        calls["gpu"] += 1
        return {
            "available": True,
            "temperature_c": 40,
            "utilization_percent": 1,
            "name": "X",
            "memory_used_mb": 1,
            "memory_total_mb": 2,
            "error": None,
        }

    monkeypatch.setattr(ms, "read_gpu_stats", fake_gpu)
    monkeypatch.setattr(
        ms,
        "read_host_stats",
        lambda: {"cpu_percent": 1, "memory_percent": 2, "disk_percent": 3},
    )
    monkeypatch.setattr(ms, "_probe_comfy_online", lambda: True)
    monkeypatch.setattr(ms, "_probe_ollama", lambda kw: (True, "m"))
    monkeypatch.setattr(
        ms,
        "job_repo",
        type(
            "J",
            (),
            {
                "list_active": lambda self, limit=50: [],
                "list_recent_failed": lambda self, limit=20: [],
            },
        )(),
    )
    monkeypatch.setattr(ms, "store", type("S", (), {"queue_depth": lambda self: 0})())
    monkeypatch.setattr(ms, "queue", type("Q", (), {"pending_count": lambda self: 0})())

    ms.build_snapshot()
    ms.build_snapshot()
    assert calls["gpu"] == 1
