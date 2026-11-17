from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.runtime import storyboard_store

client = TestClient(app)

COMPILED_H3 = """For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, the subject in <Picture 1> preserves identity and position while slowly turning toward the doorway.

overall_soundscape: Steady rain and soft fabric movement.

non_diegetic_music: N/A"""


def test_generate_video_requires_image(tmp_path: Path):
    frame = storyboard_store.create("pv1", description="x", prompt_en="a shot", image_url=None)
    with patch("app.api.storyboard.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.storyboard.client.health", return_value=True):
            r = client.post(f"/api/storyboard/pv1/frames/{frame['id']}/generate-video", json={})
    assert r.status_code == 400
    assert "image" in r.json()["detail"]


def test_generate_video_enqueues_i2v(tmp_path: Path):
    img = tmp_path / "f.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    frame = storyboard_store.create(
        "pv2",
        description="dock",
        status="completed",
        prompt_en="rainy dock night still with wardrobe lock text",
        motion_prompt_en="He turns. Slow push-in. About 5s. Keep identity from the first frame.",
        image_url=str(img),
    )
    with patch("app.api.storyboard.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.storyboard.client.health", return_value=True):
            with patch("app.api.storyboard.job_queue.enqueue") as enq:
                with patch("app.api.storyboard.job_repo.create") as create:
                    create.return_value = {"id": "job_vid1"}
                    with patch("app.services.render_compose._resolve_image_path", return_value=img):
                        with patch("app.api.storyboard.get_h3_compiler") as compiler_factory:
                            compiler_factory.return_value.compile_frame.return_value = {
                                "id": "cp_i2va",
                                "project_id": "pv2",
                                "source_type": "frame",
                                "source_id": frame["id"],
                                "source_hash": "abc",
                                "content": COMPILED_H3,
                                "validation_json": {"valid": True, "issues": []},
                                "guide_version": "minimax-h3@d21241f",
                                "stale": False,
                            }
                            r = client.post(
                                f"/api/storyboard/pv2/frames/{frame['id']}/generate-video",
                                json={},
                            )
    assert r.status_code == 200
    body = r.json()
    assert body["video_status"] == "generating"
    assert body["video_job_id"] == "job_vid1"
    enq.assert_called_once_with("job_vid1")
    payload = create.call_args.kwargs.get("payload") or create.call_args[1].get("payload")
    if payload is None:
        payload = create.call_args[1]["payload"] if create.call_args[1] else create.call_args.kwargs["payload"]
    # create called as kwargs
    kwargs = create.call_args.kwargs
    assert kwargs["payload"]["mode"] == "i2v"
    assert kwargs["payload"]["first_frame_path"] == str(img)
    assert kwargs["payload"]["prompt_en"] == COMPILED_H3
    assert kwargs["payload"]["compiled_prompt_id"] == "cp_i2va"
    assert kwargs["payload"]["length"] == 124
    assert kwargs["payload"]["legacy_accepted_frame"] is True
    assert frame["motion_prompt_en"] not in kwargs["payload"]["prompt_en"]


def test_generate_video_rejects_invalid_compilation(tmp_path: Path):
    img = tmp_path / "f.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    frame = storyboard_store.create(
        "pv_invalid", description="dock", status="completed", image_url=str(img)
    )
    with patch("app.api.storyboard.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.storyboard.client.health", return_value=True):
            with patch("app.services.render_compose._resolve_image_path", return_value=img):
                with patch("app.api.storyboard.get_h3_compiler") as factory:
                    factory.return_value.compile_frame.return_value = {
                        "id": "cp_bad",
                        "content": "bad",
                        "validation_json": {"valid": False, "issues": [{"code": "field_order"}]},
                        "stale": False,
                    }
                    with patch("app.api.storyboard.job_queue.enqueue") as enqueue:
                        response = client.post(
                            f"/api/storyboard/pv_invalid/frames/{frame['id']}/generate-video",
                            json={},
                        )
    assert response.status_code == 422
    enqueue.assert_not_called()
