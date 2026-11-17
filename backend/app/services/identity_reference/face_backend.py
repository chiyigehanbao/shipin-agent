from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Sequence

from app.services.identity_reference.types import (
    DetectedFace,
    EmbeddingFace,
    FaceBackend,
    FaceDetection,
    FaceReadiness,
    NormalizedCrop,
    PixelBox,
)


DETECTOR_FILENAME = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILENAME = "face_recognition_sface_2021dec.onnx"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def expanded_face_crop(
    *, image_width: int, image_height: int, face: PixelBox
) -> PixelBox:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("identity_crop_invalid:image_dimensions")
    side = max(float(face.width) * 1.6, float(face.height) * 1.8, 96.0)
    side = min(side, float(image_width), float(image_height))
    center_x = float(face.x) + float(face.width) / 2.0
    center_y = float(face.y) + float(face.height) * 0.42
    x = _clamp(center_x - side / 2.0, 0.0, float(image_width) - side)
    y = _clamp(center_y - side / 2.0, 0.0, float(image_height) - side)
    pixel_side = max(1, int(round(side)))
    pixel_x = int(round(x))
    pixel_y = int(round(y))
    pixel_x = min(pixel_x, image_width - pixel_side)
    pixel_y = min(pixel_y, image_height - pixel_side)
    return PixelBox(x=pixel_x, y=pixel_y, width=pixel_side, height=pixel_side)


def select_primary_face(
    faces: Sequence[DetectedFace], *, image_width: int, image_height: int
) -> DetectedFace:
    if not faces:
        raise ValueError("identity_face_missing")
    image_cx = image_width / 2.0
    image_cy = image_height / 2.0

    def rank(face: DetectedFace) -> tuple[int, float]:
        box = face.box
        area = box.width * box.height
        cx = box.x + box.width / 2.0
        cy = box.y + box.height / 2.0
        distance = math.hypot(cx - image_cx, cy - image_cy)
        return area, -distance

    return max(faces, key=rank)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class UnavailableFaceBackend:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def readiness(self) -> FaceReadiness:
        return FaceReadiness(ready=False, reason=self.reason)

    def detect(self, image_path: Path) -> FaceDetection:
        return FaceDetection(status="unavailable", reason=self.reason)

    def embedding(self, image_path: Path) -> list[float]:
        raise RuntimeError(self.reason)

    def embedding_faces(self, image_path: Path) -> list[EmbeddingFace]:
        return []


class OpenCVFaceBackend:
    def __init__(
        self,
        cv2_module: Any,
        detector_path: Path,
        recognizer_path: Path,
    ) -> None:
        self.cv2 = cv2_module
        self.detector_path = Path(detector_path)
        self.recognizer_path = Path(recognizer_path)
        self.detector = self.cv2.FaceDetectorYN_create(
            str(self.detector_path), "", (320, 320), 0.8, 0.3, 5000
        )
        self.recognizer = self.cv2.FaceRecognizerSF_create(
            str(self.recognizer_path), ""
        )
        self._fingerprint = (
            f"opencv-yunet-2023mar:{_file_sha256(self.detector_path)[:12]}+"
            f"opencv-sface-2021dec:{_file_sha256(self.recognizer_path)[:12]}"
        )

    def readiness(self) -> FaceReadiness:
        return FaceReadiness(ready=True, fingerprint=self._fingerprint)

    def _read(self, image_path: Path) -> Any:
        image = self.cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"identity_reference_invalid:{image_path.name}")
        return image

    def _raw_faces(self, image: Any) -> list[Any]:
        height, width = image.shape[:2]
        self.detector.setInputSize((int(width), int(height)))
        _status, rows = self.detector.detect(image)
        return [] if rows is None else list(rows)

    @staticmethod
    def _detected(row: Any) -> DetectedFace:
        values = [float(value) for value in row]
        landmarks = [values[index : index + 2] for index in range(4, 14, 2)]
        return DetectedFace(
            box=PixelBox(
                x=max(0, int(round(values[0]))),
                y=max(0, int(round(values[1]))),
                width=max(1, int(round(values[2]))),
                height=max(1, int(round(values[3]))),
            ),
            landmarks=landmarks,
            confidence=float(values[14]) if len(values) > 14 else 1.0,
        )

    def detect(self, image_path: Path) -> FaceDetection:
        image = self._read(image_path)
        faces = [self._detected(row) for row in self._raw_faces(image)]
        return FaceDetection(
            status="detected" if faces else "no_face",
            faces=faces,
            reason="" if faces else "identity_face_missing",
        )

    def embedding_faces(self, image_path: Path) -> list[EmbeddingFace]:
        image = self._read(image_path)
        height, width = image.shape[:2]
        result: list[EmbeddingFace] = []
        for index, row in enumerate(self._raw_faces(image)):
            detected = self._detected(row)
            aligned = self.recognizer.alignCrop(image, row)
            feature = self.recognizer.feature(aligned)
            vector = [float(value) for value in feature.reshape(-1)]
            box = detected.box
            result.append(
                EmbeddingFace(
                    face_id=f"face_{index + 1}",
                    box=NormalizedCrop(
                        x=box.x / width,
                        y=box.y / height,
                        width=box.width / width,
                        height=box.height / height,
                    ),
                    embedding=vector,
                )
            )
        return result

    def embedding(self, image_path: Path) -> list[float]:
        faces = self.embedding_faces(image_path)
        if not faces:
            raise ValueError("identity_face_missing")
        return faces[0].embedding


def build_face_backend(models_dir: Path) -> FaceBackend:
    try:
        import cv2
    except ImportError:
        return UnavailableFaceBackend("opencv_not_installed")
    detector = Path(models_dir) / DETECTOR_FILENAME
    recognizer = Path(models_dir) / RECOGNIZER_FILENAME
    if not detector.is_file() or not recognizer.is_file():
        return UnavailableFaceBackend("face_model_files_missing")
    try:
        return OpenCVFaceBackend(cv2, detector, recognizer)
    except Exception:
        return UnavailableFaceBackend("face_model_load_failed")
