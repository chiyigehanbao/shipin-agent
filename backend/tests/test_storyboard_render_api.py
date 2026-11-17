from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.repositories.storyboard_renders import (
    RenderAttemptRepository,
    RenderRequestRepository,
)
from app.main import app
from app.services.runtime import storyboard_store


client = TestClient(app)


def test_formal_submit_returns_attempt():
    formal = {
        "id": "attempt_formal",
        "adapter": "flux_kontext",
        "status": "queued",
        "is_degraded": False,
    }
    with patch("app.api.storyboard_render.get_storyboard_render_module") as factory:
        factory.return_value.submit.return_value = formal
        response = client.post(
            "/api/storyboard/p1/frames/f1/render",
            json={"seed": 42, "temporary_degradation": False},
        )
    assert response.status_code == 202
    assert response.json()["adapter"] == "flux_kontext"
    assert response.json()["status"] == "queued"


def test_temporary_degradation_is_one_attempt_only():
    results = [
        {
            "id": "attempt_degraded",
            "adapter": "text_only_flux",
            "status": "queued",
            "is_degraded": True,
        },
        {
            "id": "attempt_formal",
            "adapter": "flux_kontext",
            "status": "queued",
            "is_degraded": False,
        },
    ]
    with patch("app.api.storyboard_render.get_storyboard_render_module") as factory:
        factory.return_value.submit.side_effect = results
        degraded = client.post(
            "/api/storyboard/p1/frames/f1/render",
            json={"temporary_degradation": True},
        )
        formal = client.post(
            "/api/storyboard/p1/frames/f1/render",
            json={"temporary_degradation": False},
        )
    assert degraded.json()["is_degraded"] is True
    assert formal.json()["is_degraded"] is False
    assert formal.json()["adapter"] == "flux_kontext"


def test_review_routes_delegate_accept_reject_and_retry():
    with patch("app.api.storyboard_render.get_storyboard_render_module") as factory:
        module = factory.return_value
        module.accept.return_value = {"id": "a1", "status": "accepted"}
        module.reject.return_value = {"id": "a2", "status": "rejected"}
        module.retry.return_value = {"id": "a3", "status": "queued"}
        accepted = client.post(
            "/api/storyboard/p1/frames/f1/render-attempts/a1/accept"
        )
        rejected = client.post(
            "/api/storyboard/p1/frames/f1/render-attempts/a2/reject",
            json={"reason": "wrong_temperament", "note": "气质过于甜美"},
        )
        retried = client.post(
            "/api/storyboard/p1/frames/f1/render-attempts/a2/retry",
            json={"reuse_seed": True},
        )
    assert accepted.json()["status"] == "accepted"
    assert rejected.json()["status"] == "rejected"
    assert retried.status_code == 202
    module.reject.assert_called_once_with(
        "p1", "f1", "a2", "wrong_temperament", "气质过于甜美"
    )
    module.retry.assert_called_once_with("p1", "f1", "a2", reuse_seed=True)


def test_h3_video_requires_accepted_render():
    frame = storyboard_store.create(
        "p_candidate",
        description="candidate",
        status="completed",
        image_url="/media/assets/p_candidate/old.png",
    )
    requests = RenderRequestRepository()
    attempts = RenderAttemptRepository()
    request = requests.create(
        project_id="p_candidate",
        frame_id=frame["id"],
        source_hash="candidate-source",
        request={"compiled_prompt": "candidate"},
        validation={"valid": True, "issues": []},
    )
    attempt = attempts.create(
        request_id=request["id"],
        project_id="p_candidate",
        frame_id=frame["id"],
        adapter="flux_kontext",
        workflow_version="kontext-gguf-v1",
        model_fingerprint="unet/flux1-kontext-dev-Q4_K_S.gguf",
        seed=42,
        is_degraded=False,
    )
    attempts.transition(attempt["id"], "running")
    attempts.transition(
        attempt["id"],
        "candidate",
        image_url="/media/assets/p_candidate/candidate.png",
    )
    response = client.post(
        f"/api/storyboard/p_candidate/frames/{frame['id']}/generate-video",
        json={},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "accepted_frame_required"
