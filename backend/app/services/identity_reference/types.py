from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class NormalizedCrop(BaseModel):
    x: float
    y: float
    width: float
    height: float


class PixelBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class DetectedFace(BaseModel):
    box: PixelBox
    landmarks: list[list[float]] = Field(default_factory=list)
    confidence: float = 1.0


class FaceDetection(BaseModel):
    status: Literal["detected", "no_face", "unavailable"]
    faces: list[DetectedFace] = Field(default_factory=list)
    reason: str = ""


class FaceReadiness(BaseModel):
    ready: bool
    reason: str = ""
    fingerprint: str = ""


@dataclass(frozen=True)
class EmbeddingFace:
    face_id: str
    box: NormalizedCrop
    embedding: list[float]


class FaceBackend(Protocol):
    def readiness(self) -> FaceReadiness: ...

    def detect(self, image_path: Path) -> FaceDetection: ...

    def embedding(self, image_path: Path) -> list[float]: ...

    def embedding_faces(self, image_path: Path) -> list[EmbeddingFace]: ...
