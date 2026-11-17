from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.asset_store import AssetStore
from app.services.identity_reference.face_backend import (
    expanded_face_crop,
    select_primary_face,
)
from app.services.identity_reference.types import FaceBackend, NormalizedCrop, PixelBox


IDENTITY_SIZE = 768
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class IdentityReferenceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field

    def detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field:
            detail["field"] = self.field
        return detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


class IdentityReferenceService:
    def __init__(
        self,
        *,
        assets: AssetStore,
        face_backend: FaceBackend,
        media_root: Path,
        output_root: Path,
    ) -> None:
        self.assets = assets
        self.face_backend = face_backend
        self.media_root = Path(media_root).resolve()
        self.output_root = Path(output_root).resolve()

    def _asset(self, project_id: str, asset_id: str) -> dict[str, Any]:
        asset = self.assets.get(project_id, asset_id)
        if asset is None:
            raise IdentityReferenceError(
                "identity_asset_not_found", "人物资产不存在。", status_code=404
            )
        if asset.get("type") != "character":
            raise IdentityReferenceError(
                "identity_asset_invalid", "只有人物资产可以设置身份引用。", status_code=422
            )
        if asset.get("status") != "completed" or asset.get("selection_status") != "selected":
            raise IdentityReferenceError(
                "identity_asset_not_ready",
                "请先选择一个已完成的人物定妆资产。",
                status_code=409,
            )
        return asset

    def _source_path(self, asset: dict[str, Any]) -> Path:
        image_url = str(asset.get("image_url") or "")
        prefix = "/media/"
        if not image_url.startswith(prefix):
            raise IdentityReferenceError(
                "identity_reference_invalid",
                "人物定妆图不是可读取的本地媒体文件。",
                status_code=422,
                field="image_url",
            )
        relative = Path(image_url.removeprefix(prefix))
        source = (self.media_root / relative).resolve()
        if not source.is_relative_to(self.media_root) or not source.is_file():
            raise IdentityReferenceError(
                "identity_reference_invalid",
                "人物定妆图路径无效或文件不存在。",
                status_code=422,
                field="image_url",
            )
        return source

    def _candidate_path(self, project_id: str, candidate_id: str) -> Path:
        directory = self.output_root / project_id / "identity"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{candidate_id}.png"

    def _media_url(self, path: Path) -> str:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.media_root):
            raise IdentityReferenceError(
                "identity_storage_invalid",
                "身份引用输出目录不在媒体目录中。",
                status_code=500,
            )
        return "/media/" + resolved.relative_to(self.media_root).as_posix()

    @staticmethod
    def _pixel_crop(crop: NormalizedCrop, width: int, height: int) -> PixelBox:
        values = (crop.x, crop.y, crop.width, crop.height)
        if (
            any(value < 0.0 or value > 1.0 for value in values)
            or crop.width <= 0.0
            or crop.height <= 0.0
            or crop.x + crop.width > 1.0
            or crop.y + crop.height > 1.0
        ):
            raise IdentityReferenceError(
                "identity_crop_invalid",
                "裁剪框必须完整位于图片范围内。",
                status_code=422,
                field="crop",
            )
        box = PixelBox(
            x=int(round(crop.x * width)),
            y=int(round(crop.y * height)),
            width=int(round(crop.width * width)),
            height=int(round(crop.height * height)),
        )
        if box.width < 96 or box.height < 96:
            raise IdentityReferenceError(
                "identity_crop_invalid",
                "裁剪区域过小，宽和高至少需要 96 像素。",
                status_code=422,
                field="crop",
            )
        box.width = min(box.width, width - box.x)
        box.height = min(box.height, height - box.y)
        return box

    @staticmethod
    def _normalized_crop(box: PixelBox, width: int, height: int) -> dict[str, float]:
        return NormalizedCrop(
            x=box.x / width,
            y=box.y / height,
            width=box.width / width,
            height=box.height / height,
        ).model_dump()

    @staticmethod
    def _save_crop(image: Image.Image, box: PixelBox, output: Path) -> None:
        cropped = image.crop((box.x, box.y, box.x + box.width, box.y + box.height))
        normalized = ImageOps.fit(
            cropped.convert("RGB"),
            (IDENTITY_SIZE, IDENTITY_SIZE),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.42),
        )
        normalized.save(output, format="PNG", optimize=True)

    @staticmethod
    def _save_upload(payload: bytes, output: Path) -> None:
        if not payload or len(payload) > MAX_UPLOAD_BYTES:
            raise IdentityReferenceError(
                "identity_upload_invalid",
                "上传图片为空或超过 20MB。",
                status_code=422,
                field="file",
            )
        try:
            with Image.open(BytesIO(payload)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                normalized = ImageOps.fit(
                    image,
                    (IDENTITY_SIZE, IDENTITY_SIZE),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.42),
                )
                normalized.save(output, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise IdentityReferenceError(
                "identity_upload_invalid",
                "上传文件不是可用的图片。",
                status_code=422,
                field="file",
            ) from exc

    def _quality(self, path: Path) -> tuple[int | None, str, str]:
        detection = self.face_backend.detect(path)
        fingerprint = self.face_backend.readiness().fingerprint
        if detection.status == "unavailable":
            return None, "unscored", fingerprint
        count = len(detection.faces)
        return count, "good" if count == 1 else "review", fingerprint

    def _append_candidate(
        self,
        *,
        asset: dict[str, Any],
        candidate_id: str,
        source_type: str,
        source_image_url: str,
        output: Path,
        crop: dict[str, float] | None,
        face_count: int | None,
        quality: str,
        detector_fingerprint: str,
    ) -> dict[str, Any]:
        candidate: dict[str, Any] = {
            "id": candidate_id,
            "status": "pending",
            "source_type": source_type,
            "source_image_url": source_image_url,
            "image_url": self._media_url(output),
            "image_hash": _sha256(output),
            "crop": crop,
            "face_count": face_count,
            "quality": quality,
            "detector_fingerprint": detector_fingerprint,
            "created_at": _now(),
        }
        identity = dict(asset.get("identity") or {})
        candidates = list(identity.get("reference_candidates") or [])
        candidates.append(candidate)
        identity["reference_candidates"] = candidates
        self.assets.update(asset["project_id"], asset["id"], identity=identity)
        return candidate

    def create_auto_candidate(self, project_id: str, asset_id: str) -> dict[str, Any]:
        asset = self._asset(project_id, asset_id)
        source = self._source_path(asset)
        detection = self.face_backend.detect(source)
        if detection.status == "unavailable":
            raise IdentityReferenceError(
                "face_model_unavailable",
                f"本地人脸模型不可用：{detection.reason or 'unknown'}",
                status_code=409,
            )
        if detection.status == "no_face" or not detection.faces:
            raise IdentityReferenceError(
                "identity_face_missing",
                "定妆图中没有检测到可用人脸，请手动裁剪或上传身份照。",
                status_code=422,
            )
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
            face = select_primary_face(
                detection.faces, image_width=image.width, image_height=image.height
            )
            box = expanded_face_crop(
                image_width=image.width, image_height=image.height, face=face.box
            )
            candidate_id = f"identity_{uuid.uuid4().hex[:12]}"
            output = self._candidate_path(project_id, candidate_id)
            self._save_crop(image, box, output)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise IdentityReferenceError(
                "identity_reference_invalid",
                "人物定妆图无法读取或裁剪。",
                status_code=422,
            ) from exc
        readiness = self.face_backend.readiness()
        return self._append_candidate(
            asset=asset,
            candidate_id=candidate_id,
            source_type="auto_crop",
            source_image_url=str(asset["image_url"]),
            output=output,
            crop=self._normalized_crop(box, image.width, image.height),
            face_count=len(detection.faces),
            quality="good" if len(detection.faces) == 1 else "review",
            detector_fingerprint=readiness.fingerprint,
        )

    def create_crop_candidate(
        self, project_id: str, asset_id: str, crop: NormalizedCrop
    ) -> dict[str, Any]:
        asset = self._asset(project_id, asset_id)
        source = self._source_path(asset)
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
            box = self._pixel_crop(crop, image.width, image.height)
            candidate_id = f"identity_{uuid.uuid4().hex[:12]}"
            output = self._candidate_path(project_id, candidate_id)
            self._save_crop(image, box, output)
        except IdentityReferenceError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise IdentityReferenceError(
                "identity_reference_invalid",
                "人物定妆图无法读取或裁剪。",
                status_code=422,
            ) from exc
        face_count, quality, fingerprint = self._quality(output)
        return self._append_candidate(
            asset=asset,
            candidate_id=candidate_id,
            source_type="manual_crop",
            source_image_url=str(asset["image_url"]),
            output=output,
            crop=crop.model_dump(),
            face_count=face_count,
            quality=quality,
            detector_fingerprint=fingerprint,
        )

    def create_upload_candidate(
        self,
        project_id: str,
        asset_id: str,
        payload: bytes,
        *,
        filename: str = "identity.png",
    ) -> dict[str, Any]:
        asset = self._asset(project_id, asset_id)
        candidate_id = f"identity_{uuid.uuid4().hex[:12]}"
        output = self._candidate_path(project_id, candidate_id)
        try:
            self._save_upload(payload, output)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        face_count, quality, fingerprint = self._quality(output)
        return self._append_candidate(
            asset=asset,
            candidate_id=candidate_id,
            source_type="upload",
            source_image_url=filename,
            output=output,
            crop=None,
            face_count=face_count,
            quality=quality,
            detector_fingerprint=fingerprint,
        )

    def register_generated(
        self,
        project_id: str,
        asset_id: str,
        generated_path: Path,
        *,
        source_image_url: str,
    ) -> dict[str, Any]:
        asset = self._asset(project_id, asset_id)
        source = Path(generated_path).resolve()
        if not source.is_relative_to(self.media_root) or not source.is_file():
            raise IdentityReferenceError(
                "identity_reference_invalid",
                "生成的标准身份照文件无效。",
                status_code=422,
            )
        candidate_id = f"identity_{uuid.uuid4().hex[:12]}"
        output = self._candidate_path(project_id, candidate_id)
        try:
            self._save_upload(source.read_bytes(), output)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        face_count, quality, fingerprint = self._quality(output)
        return self._append_candidate(
            asset=asset,
            candidate_id=candidate_id,
            source_type="generated",
            source_image_url=source_image_url,
            output=output,
            crop=None,
            face_count=face_count,
            quality=quality,
            detector_fingerprint=fingerprint,
        )

    def confirm_candidate(
        self, project_id: str, asset_id: str, candidate_id: str
    ) -> dict[str, Any]:
        asset = self._asset(project_id, asset_id)
        identity = dict(asset.get("identity") or {})
        candidates = list(identity.get("reference_candidates") or [])
        candidate = next(
            (item for item in candidates if item.get("id") == candidate_id), None
        )
        if candidate is None:
            raise IdentityReferenceError(
                "identity_candidate_not_found", "身份引用候选不存在。", status_code=404
            )
        current = dict(identity.get("reference") or {})
        reference = dict(candidate)
        reference["status"] = "ready"
        reference["version"] = int(current.get("version") or 0) + 1
        reference["confirmed_at"] = _now()
        identity["reference"] = reference
        identity["reference_candidates"] = [
            item for item in candidates if item.get("id") != candidate_id
        ]
        self.assets.update(project_id, asset_id, identity=identity)
        return self.get_state(project_id, asset_id)

    def get_state(self, project_id: str, asset_id: str) -> dict[str, Any]:
        asset = self._asset(project_id, asset_id)
        identity = dict(asset.get("identity") or {})
        readiness = self.face_backend.readiness()
        return {
            "asset_id": asset_id,
            "source_image_url": asset.get("image_url"),
            "reference": identity.get("reference"),
            "candidates": list(identity.get("reference_candidates") or []),
            "face_model": readiness.model_dump(),
        }
