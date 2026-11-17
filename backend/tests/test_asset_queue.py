import time
from pathlib import Path
from unittest.mock import MagicMock

from app.services.asset_store import AssetStore
from app.services.asset_queue import AssetQueue


def test_enqueue_sets_generating_then_completed(tmp_path):
    store = AssetStore(tmp_path / "a.db")
    client = MagicMock()
    client.health.return_value = True
    client.submit_workflow.return_value = "pid-1"
    client.poll_history.return_value = {
        "filename": "x.png",
        "subfolder": "",
        "type": "output",
    }

    def fake_download(meta, dest: Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"PNG")
        return dest

    client.download_image.side_effect = fake_download

    q = AssetQueue(
        store=store,
        client=client,
        output_root=tmp_path,
        build_workflow=lambda model, prompt, negative="", **kw: {"ok": True},
        poll_timeout_sec=5.0,
        poll_interval_sec=0.01,
    )
    q.start()
    asset = store.create(
        project_id="p1",
        name="A",
        type="character",
        prompt_cn="猫",
        prompt_en="a cat",
        model="flux",
    )
    q.enqueue("p1", asset["id"])
    for _ in range(100):
        cur = store.get("p1", asset["id"])
        if cur["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    q.stop()
    cur = store.get("p1", asset["id"])
    assert cur["status"] == "completed"
    assert cur["image_url"].endswith(".png")
    assert Path(tmp_path / "p1" / f"{asset['id']}.png").exists()


def test_comfyui_down_fails_fast(tmp_path):
    store = AssetStore(tmp_path / "b.db")
    client = MagicMock()
    client.health.return_value = False
    q = AssetQueue(
        store=store,
        client=client,
        output_root=tmp_path,
        build_workflow=lambda m, p, negative="": {},
    )
    q.start()
    asset = store.create(
        project_id="p1",
        name="B",
        type="scene",
        prompt_cn="x",
        prompt_en="",
        model="flux",
    )
    q.enqueue("p1", asset["id"])
    for _ in range(100):
        cur = store.get("p1", asset["id"])
        if cur["status"] == "failed":
            break
        time.sleep(0.05)
    q.stop()
    assert store.get("p1", asset["id"])["error"] == "comfyui_unavailable"
