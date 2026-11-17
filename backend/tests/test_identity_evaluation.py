from pathlib import Path

import pytest

from app.services.identity_reference.evaluation import (
    IdentityEvaluationService,
    best_identity_assignment,
    cosine_similarity,
    identity_risk,
)
from app.services.identity_reference.types import (
    EmbeddingFace,
    FaceReadiness,
    NormalizedCrop,
)
from app.services.storyboard_render.types import CharacterIdentity


def _face(face_id: str, x: float, vector: list[float]) -> EmbeddingFace:
    return EmbeddingFace(
        face_id=face_id,
        box=NormalizedCrop(x=x, y=0.1, width=0.35, height=0.55),
        embedding=vector,
    )


def test_two_person_matching_never_reuses_candidate_face():
    result = best_identity_assignment(
        references={"woman": [1.0, 0.0], "man": [0.0, 1.0]},
        candidates=[
            _face("left", 0.05, [0.95, 0.05]),
            _face("right", 0.60, [0.02, 0.98]),
        ],
    )

    assert result["woman"].face_id == "left"
    assert result["man"].face_id == "right"
    assert len({match.face_id for match in result.values()}) == 2


def test_assignment_leaves_one_identity_unmatched_when_only_one_face_exists():
    result = best_identity_assignment(
        references={"woman": [1.0, 0.0], "man": [0.0, 1.0]},
        candidates=[_face("only", 0.2, [0.02, 0.98])],
    )
    assert list(result) == ["man"]


@pytest.mark.parametrize(
    ("score", "risk"),
    [(0.50, "stable"), (0.49, "review"), (0.35, "review"), (0.34, "high_risk")],
)
def test_risk_thresholds(score: float, risk: str):
    assert identity_risk(score) == risk


def test_cosine_similarity_handles_zero_vector():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class FakeEvaluationBackend:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready

    def readiness(self) -> FaceReadiness:
        return FaceReadiness(
            ready=self.ready,
            reason="" if self.ready else "face_model_files_missing",
            fingerprint="fake-sface-v1" if self.ready else "",
        )

    def embedding(self, image_path: Path) -> list[float]:
        return [1.0, 0.0] if "woman" in image_path.name else [0.0, 1.0]

    def embedding_faces(self, image_path: Path) -> list[EmbeddingFace]:
        return [
            _face("left", 0.05, [0.90, 0.10]),
            _face("right", 0.60, [0.10, 0.90]),
        ]


def _identity(asset_id: str, name: str, image_name: str, order: int):
    return CharacterIdentity(
        character_asset_id=asset_id,
        character_name=name,
        reference_asset_id=asset_id,
        reference_image_url=f"/media/identity/{image_name}",
        reference_image_hash=f"sha256:{asset_id}",
        identity_anchor="stable face",
        reference_order=order,
        reference_source_type="manual_crop",
        reference_version=1,
    )


def test_evaluation_service_scores_two_characters(tmp_path: Path):
    media_root = tmp_path / "media"
    identity_dir = media_root / "identity"
    identity_dir.mkdir(parents=True)
    (identity_dir / "woman.png").write_bytes(b"woman")
    (identity_dir / "man.png").write_bytes(b"man")
    candidate = media_root / "candidate.png"
    candidate.write_bytes(b"candidate")
    service = IdentityEvaluationService(
        face_backend=FakeEvaluationBackend(), media_root=media_root
    )

    result = service.evaluate(
        [
            _identity("woman", "苏遥", "woman.png", 1),
            _identity("man", "林默", "man.png", 2),
        ],
        candidate,
    )

    assert result["status"] == "scored"
    assert result["model_fingerprint"] == "fake-sface-v1"
    assert [item["risk"] for item in result["characters"]] == ["stable", "stable"]
    assert result["warnings"] == []


def test_evaluation_service_reports_unavailable_without_reading_files(tmp_path: Path):
    service = IdentityEvaluationService(
        face_backend=FakeEvaluationBackend(ready=False), media_root=tmp_path
    )
    result = service.evaluate(
        [_identity("woman", "苏遥", "missing.png", 1)],
        tmp_path / "missing-candidate.png",
    )
    assert result == {
        "status": "unscored",
        "model_fingerprint": "",
        "characters": [],
        "warnings": ["face_model_unavailable"],
    }
