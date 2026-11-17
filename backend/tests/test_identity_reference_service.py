from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.services.asset_store import AssetStore
from app.services.identity_reference.service import (
    IdentityReferenceError,
    IdentityReferenceService,
)
from app.services.identity_reference.types import (
    DetectedFace,
    EmbeddingFace,
    FaceDetection,
    FaceReadiness,
    NormalizedCrop,
    PixelBox,
)


class FakeFaceBackend:
    def __init__(self, detection: FaceDetection | None = None) -> None:
        self._detection = detection or FaceDetection(
            status="detected",
            faces=[DetectedFace(box=PixelBox(x=350, y=210, width=260, height=320))],
        )

    def readiness(self) -> FaceReadiness:
        return FaceReadiness(ready=True, fingerprint="fake-face-v1")

    def detect(self, image_path: Path) -> FaceDetection:
        return self._detection

    def embedding(self, image_path: Path) -> list[float]:
        return [1.0, 0.0]

    def embedding_faces(self, image_path: Path) -> list[EmbeddingFace]:
        return []


def _png_bytes(size: tuple[int, int] = (1024, 1024)) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, (184, 139, 121)).save(stream, format="PNG")
    return stream.getvalue()


def _selected_character(
    tmp_path: Path, *, identity: dict | None = None
) -> tuple[AssetStore, dict, Path, Path]:
    media_root = tmp_path / "media"
    output_root = media_root / "assets"
    source = media_root / "projects" / "p1" / "casting.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png_bytes())
    store = AssetStore(tmp_path / "assets.db")
    asset = store.create(
        project_id="p1",
        name="苏瑶",
        type="character",
        prompt_cn="",
        prompt_en="",
        model="flux",
        status="completed",
        selection_status="selected",
        identity=identity,
    )
    asset = store.update(
        "p1",
        asset["id"],
        image_url="/media/projects/p1/casting.png",
    )
    return store, asset, media_root, output_root


def test_auto_candidate_waits_for_confirmation_and_preserves_source(tmp_path: Path):
    store, asset, media_root, output_root = _selected_character(tmp_path)
    service = IdentityReferenceService(
        assets=store,
        face_backend=FakeFaceBackend(),
        media_root=media_root,
        output_root=output_root,
    )

    candidate = service.create_auto_candidate("p1", asset["id"])

    unchanged = store.get("p1", asset["id"])
    assert unchanged is not None
    assert unchanged["image_url"] == asset["image_url"]
    assert "reference" not in unchanged["identity"]
    assert candidate["status"] == "pending"
    assert candidate["source_type"] == "auto_crop"
    assert candidate["image_hash"].startswith("sha256:")
    assert candidate["face_count"] == 1
    candidate_path = media_root / candidate["image_url"].removeprefix("/media/")
    assert candidate_path.is_file()
    with Image.open(candidate_path) as image:
        assert image.size == (768, 768)

    state = service.confirm_candidate("p1", asset["id"], candidate["id"])

    assert state["reference"]["version"] == 1
    assert state["reference"]["status"] == "ready"
    assert state["reference"]["source_type"] == "auto_crop"
    assert state["reference"]["image_url"] == candidate["image_url"]
    assert state["candidates"] == []
    confirmed = store.get("p1", asset["id"])
    assert confirmed is not None
    assert confirmed["image_url"] == asset["image_url"]


def test_manual_crop_creates_candidate_and_rejects_too_small_crop(tmp_path: Path):
    store, asset, media_root, output_root = _selected_character(tmp_path)
    service = IdentityReferenceService(
        assets=store,
        face_backend=FakeFaceBackend(),
        media_root=media_root,
        output_root=output_root,
    )
    crop = NormalizedCrop(x=0.2, y=0.1, width=0.5, height=0.5)

    candidate = service.create_crop_candidate("p1", asset["id"], crop)

    assert candidate["source_type"] == "manual_crop"
    assert candidate["crop"] == crop.model_dump()
    with pytest.raises(IdentityReferenceError) as exc_info:
        service.create_crop_candidate(
            "p1",
            asset["id"],
            NormalizedCrop(x=0.0, y=0.0, width=0.02, height=0.02),
        )
    assert exc_info.value.code == "identity_crop_invalid"
    assert "reference" not in store.get("p1", asset["id"])["identity"]


@pytest.mark.parametrize(
    ("detection", "expected_code", "expected_status"),
    [
        (FaceDetection(status="no_face"), "identity_face_missing", 422),
        (
            FaceDetection(status="unavailable", reason="face_model_files_missing"),
            "face_model_unavailable",
            409,
        ),
    ],
)
def test_auto_failure_does_not_replace_confirmed_reference(
    tmp_path: Path,
    detection: FaceDetection,
    expected_code: str,
    expected_status: int,
):
    current = {
        "reference": {
            "image_url": "/media/assets/p1/identity/existing.png",
            "version": 3,
            "source_type": "upload",
        }
    }
    store, asset, media_root, output_root = _selected_character(
        tmp_path, identity=current
    )
    service = IdentityReferenceService(
        assets=store,
        face_backend=FakeFaceBackend(detection),
        media_root=media_root,
        output_root=output_root,
    )

    with pytest.raises(IdentityReferenceError) as exc_info:
        service.create_auto_candidate("p1", asset["id"])

    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == expected_status
    assert store.get("p1", asset["id"])["identity"]["reference"]["version"] == 3


def test_upload_creates_normalized_candidate_even_when_detector_unavailable(
    tmp_path: Path,
):
    store, asset, media_root, output_root = _selected_character(tmp_path)
    service = IdentityReferenceService(
        assets=store,
        face_backend=FakeFaceBackend(
            FaceDetection(status="unavailable", reason="face_model_files_missing")
        ),
        media_root=media_root,
        output_root=output_root,
    )

    candidate = service.create_upload_candidate(
        "p1", asset["id"], _png_bytes((640, 960)), filename="portrait.png"
    )

    assert candidate["source_type"] == "upload"
    assert candidate["quality"] == "unscored"
    candidate_path = media_root / candidate["image_url"].removeprefix("/media/")
    with Image.open(candidate_path) as image:
        assert image.size == (768, 768)


def test_rejects_source_media_path_that_escapes_media_root(tmp_path: Path):
    store, asset, media_root, output_root = _selected_character(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png_bytes())
    store.update(
        "p1",
        asset["id"],
        image_url="/media/../outside.png",
    )
    service = IdentityReferenceService(
        assets=store,
        face_backend=FakeFaceBackend(),
        media_root=media_root,
        output_root=output_root,
    )

    with pytest.raises(IdentityReferenceError) as exc_info:
        service.create_auto_candidate("p1", asset["id"])

    assert exc_info.value.code == "identity_reference_invalid"
