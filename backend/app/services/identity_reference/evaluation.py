from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations, permutations
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.services.identity_reference.types import (
    EmbeddingFace,
    FaceBackend,
    NormalizedCrop,
)
from app.services.storyboard_render.types import CharacterIdentity


@dataclass(frozen=True)
class IdentityMatch:
    face_id: str
    box: NormalizedCrop
    similarity: float


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("identity_embedding_dimension_mismatch")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    score = sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
    return max(-1.0, min(1.0, score))


def best_identity_assignment(
    references: dict[str, list[float]], candidates: list[EmbeddingFace]
) -> dict[str, IdentityMatch]:
    names = list(references)
    count = min(len(names), len(candidates))
    if count == 0:
        return {}
    best: tuple[float, tuple[str, ...], tuple[EmbeddingFace, ...]] | None = None
    for selected_names in combinations(names, count):
        for ordered_faces in permutations(candidates, count):
            total = sum(
                cosine_similarity(references[name], face.embedding)
                for name, face in zip(
                    selected_names, ordered_faces, strict=True
                )
            )
            if best is None or total > best[0]:
                best = (total, selected_names, ordered_faces)
    assert best is not None
    return {
        name: IdentityMatch(
            face_id=face.face_id,
            box=face.box,
            similarity=cosine_similarity(references[name], face.embedding),
        )
        for name, face in zip(best[1], best[2], strict=True)
    }


def identity_risk(score: float) -> str:
    if score >= 0.50:
        return "stable"
    if score >= 0.35:
        return "review"
    return "high_risk"


class IdentityEvaluationService:
    def __init__(self, *, face_backend: FaceBackend, media_root: Path) -> None:
        self.face_backend = face_backend
        self.media_root = Path(media_root).resolve()

    def _resolve_media_url(self, public_url: str) -> Path:
        url_path = unquote(urlparse(public_url).path)
        if not url_path.startswith("/media/"):
            raise ValueError("identity_reference_invalid")
        resolved = (self.media_root / url_path.removeprefix("/media/")).resolve()
        if not resolved.is_relative_to(self.media_root) or not resolved.is_file():
            raise ValueError("identity_reference_invalid")
        return resolved

    def _candidate_path(self, candidate_path: Path) -> Path:
        resolved = Path(candidate_path).resolve()
        if not resolved.is_relative_to(self.media_root) or not resolved.is_file():
            raise ValueError("identity_candidate_invalid")
        return resolved

    def evaluate(
        self,
        identities: list[CharacterIdentity],
        candidate_path: Path,
    ) -> dict:
        readiness = self.face_backend.readiness()
        if not readiness.ready:
            return {
                "status": "unscored",
                "model_fingerprint": readiness.fingerprint,
                "characters": [],
                "warnings": ["face_model_unavailable"],
            }
        reference_vectors = {
            identity.character_asset_id: self.face_backend.embedding(
                self._resolve_media_url(identity.reference_image_url)
            )
            for identity in identities
        }
        candidate_faces = self.face_backend.embedding_faces(
            self._candidate_path(candidate_path)
        )
        matches = best_identity_assignment(reference_vectors, candidate_faces)
        return self._serialize(identities, matches, readiness.fingerprint)

    @staticmethod
    def _serialize(
        identities: list[CharacterIdentity],
        matches: dict[str, IdentityMatch],
        model_fingerprint: str,
    ) -> dict:
        characters = []
        for identity in identities:
            match = matches.get(identity.character_asset_id)
            characters.append(
                {
                    "character_asset_id": identity.character_asset_id,
                    "character_name": identity.character_name,
                    "similarity": match.similarity if match else None,
                    "risk": identity_risk(match.similarity) if match else "unscored",
                    "candidate_face": (
                        match.box.model_dump(mode="json") if match else None
                    ),
                }
            )
        missing = any(item["similarity"] is None for item in characters)
        return {
            "status": (
                "scored"
                if any(item["similarity"] is not None for item in characters)
                else "unscored"
            ),
            "model_fingerprint": model_fingerprint,
            "characters": characters,
            "warnings": ["candidate_face_missing"] if missing else [],
        }
