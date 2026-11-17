from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.identity_reference.service import IdentityReferenceError


client = TestClient(app)


def test_identity_reference_routes_delegate_lifecycle_actions():
    state = {
        "asset_id": "char1",
        "source_image_url": "/media/casting.png",
        "reference": None,
        "candidates": [],
        "face_model": {"ready": True, "reason": "", "fingerprint": "fake"},
    }
    candidate = {"id": "identity_1", "status": "pending"}
    with patch(
        "app.api.identity_references.get_identity_reference_service"
    ) as factory:
        service = factory.return_value
        service.get_state.return_value = state
        service.create_auto_candidate.return_value = candidate
        service.create_crop_candidate.return_value = candidate
        service.confirm_candidate.return_value = {**state, "reference": candidate}

        fetched = client.get("/api/assets/p1/char1/identity-reference")
        automatic = client.post("/api/assets/p1/char1/identity-reference/auto")
        cropped = client.post(
            "/api/assets/p1/char1/identity-reference/crop",
            json={"x": 0.2, "y": 0.1, "width": 0.5, "height": 0.5},
        )
        confirmed = client.post(
            "/api/assets/p1/char1/identity-reference/confirm",
            json={"candidate_id": "identity_1"},
        )

    assert fetched.status_code == 200
    assert automatic.status_code == 201
    assert cropped.status_code == 201
    assert confirmed.status_code == 200
    service.get_state.assert_called_once_with("p1", "char1")
    service.create_auto_candidate.assert_called_once_with("p1", "char1")
    service.create_crop_candidate.assert_called_once()
    crop = service.create_crop_candidate.call_args.args[2]
    assert crop.model_dump() == {"x": 0.2, "y": 0.1, "width": 0.5, "height": 0.5}
    service.confirm_candidate.assert_called_once_with("p1", "char1", "identity_1")


def test_identity_reference_upload_passes_file_bytes():
    with patch(
        "app.api.identity_references.get_identity_reference_service"
    ) as factory:
        factory.return_value.create_upload_candidate.return_value = {
            "id": "identity_upload",
            "source_type": "upload",
        }
        response = client.post(
            "/api/assets/p1/char1/identity-reference/upload",
            files={"file": ("portrait.png", b"png-payload", "image/png")},
        )

    assert response.status_code == 201
    factory.return_value.create_upload_candidate.assert_called_once_with(
        "p1", "char1", b"png-payload", filename="portrait.png"
    )


def test_identity_reference_errors_have_stable_code_and_status():
    with patch(
        "app.api.identity_references.get_identity_reference_service"
    ) as factory:
        factory.return_value.create_auto_candidate.side_effect = IdentityReferenceError(
            "face_model_unavailable",
            "本地人脸模型不可用。",
            status_code=409,
        )
        response = client.post("/api/assets/p1/char1/identity-reference/auto")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "face_model_unavailable",
        "message": "本地人脸模型不可用。",
    }


def test_generate_identity_reference_enqueues_explicit_job():
    asset = {
        "id": "char1",
        "name": "苏遥",
        "type": "character",
        "status": "completed",
        "selection_status": "selected",
        "image_url": "/media/casting.png",
    }
    job = {"id": "job_identity", "type": "identity_reference_generate", "status": "queued"}
    with patch(
        "app.api.identity_references.get_identity_reference_job_runtime"
    ) as factory:
        job_repo, job_queue, assets = (MagicMock(), MagicMock(), MagicMock())
        factory.return_value = (job_repo, job_queue, assets)
        assets.get.return_value = asset
        job_repo.create.return_value = job

        response = client.post(
            "/api/assets/p1/char1/identity-reference/generate",
            json={"seed": 42},
        )

    assert response.status_code == 202
    job_repo.create.assert_called_once_with(
        type="identity_reference_generate",
        project_id="p1",
        title="标准身份照 · 苏遥",
        payload={"asset_id": "char1", "seed": 42},
        link_path="/workbench/p1/assets",
    )
    job_queue.enqueue.assert_called_once_with("job_identity")
