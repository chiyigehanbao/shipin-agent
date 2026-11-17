from pathlib import Path

import pytest

from app.db.repositories.frames import FrameRepository
from app.db.repositories.storyboard_renders import (
    RenderAttemptRepository,
    RenderRequestRepository,
)


def test_request_is_immutable_and_attempt_transition_is_guarded(tmp_path: Path):
    db = tmp_path / "render.db"
    requests = RenderRequestRepository(db)
    attempts = RenderAttemptRepository(db)
    request = requests.create(
        project_id="p1",
        frame_id="f1",
        source_hash="source-1",
        request={"compiled_prompt": "preserve identity"},
        validation={"valid": True, "issues": []},
    )
    assert requests.get(request["id"])["request"]["compiled_prompt"] == (
        "preserve identity"
    )
    assert requests.latest_for_frame("p1", "f1")["id"] == request["id"]
    assert not hasattr(requests, "update")

    attempt = attempts.create(
        request_id=request["id"],
        project_id="p1",
        frame_id="f1",
        adapter="flux_kontext",
        workflow_version="kontext-gguf-v1",
        model_fingerprint="unet/flux1-kontext-dev-Q4_K_S.gguf",
        seed=42,
        is_degraded=False,
    )
    running = attempts.transition(attempt["id"], "running")
    candidate = attempts.transition(
        running["id"], "candidate", image_url="/media/assets/p1/candidate.png"
    )
    assert candidate["status"] == "candidate"
    accepted = attempts.transition(candidate["id"], "accepted")
    assert accepted["status"] == "accepted"
    assert attempts.list_for_frame("p1", "f1")[0]["model_fingerprint"].endswith(
        "Q4_K_S.gguf"
    )
    with pytest.raises(ValueError, match="invalid_attempt_transition"):
        attempts.transition(accepted["id"], "running")


def test_attempt_job_failure_and_frame_accepted_attempt_roundtrip(tmp_path: Path):
    db = tmp_path / "render-state.db"
    attempts = RenderAttemptRepository(db)
    attempt = attempts.create(
        request_id="request-1",
        project_id="p1",
        frame_id="f1",
        adapter="flux_kontext",
        workflow_version="kontext-gguf-v1",
        model_fingerprint="unet/model.gguf",
        seed=7,
        is_degraded=True,
    )
    attached = attempts.attach_job(attempt["id"], "job-1")
    assert attached["job_id"] == "job-1"
    assert attached["is_degraded"] is True
    attempts.transition(attempt["id"], "running")
    assert attempts.fail_inflight(error="server_restarted") == 1
    failed = attempts.get(attempt["id"])
    assert failed["status"] == "failed"
    assert failed["error"] == {"code": "server_restarted"}

    frames = FrameRepository(db)
    frame = frames.create("p1", id="f1")
    assert frame["accepted_render_attempt_id"] is None
    updated = frames.update(
        "p1", "f1", accepted_render_attempt_id=attempt["id"]
    )
    assert updated["accepted_render_attempt_id"] == attempt["id"]


def test_storyboard_attempt_identity_evaluation_roundtrip(tmp_path: Path):
    repo = RenderAttemptRepository(tmp_path / "evaluation.db")
    attempt = repo.create(
        request_id="rr_1",
        project_id="p1",
        frame_id="f1",
        adapter="flux_kontext",
        workflow_version="kontext-gguf-v1",
        model_fingerprint="unet/flux1-kontext-dev-Q4_K_S.gguf",
        seed=42,
        is_degraded=False,
    )
    result = repo.set_identity_evaluation(
        attempt["id"],
        {
            "status": "scored",
            "model_fingerprint": "opencv-sface-2021dec",
            "characters": [
                {
                    "character_asset_id": "a1",
                    "similarity": 0.57,
                    "risk": "stable",
                }
            ],
            "warnings": [],
        },
    )
    assert result["identity_evaluation"]["characters"][0]["risk"] == "stable"
