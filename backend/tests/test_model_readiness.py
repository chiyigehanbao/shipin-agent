import hashlib
import json
from pathlib import Path

from app.services.model_readiness import (
    REQUIRED_FILES,
    check_all_models,
    check_face_identity_models,
    check_model,
)


def _touch(root: Path, rel: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_flux_not_ready_when_vae_missing(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    for rel in REQUIRED_FILES["flux"]:
        if rel.endswith("ae.safetensors"):
            continue
        _touch(models, rel)
    result = check_model("flux", models)
    assert result["ready"] is False
    assert "vae/ae.safetensors" in result["missing_files"]


def test_check_all_models_keys(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    models.mkdir(parents=True)
    all_r = check_all_models(models)
    assert set(all_r.keys()) == {"flux", "flux_kontext", "minimax"}


def test_flux_kontext_ready_when_all_files_exist(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    for rel in REQUIRED_FILES["flux_kontext"]:
        _touch(models, rel)
    result = check_model("flux_kontext", models)
    assert result == {"ready": True, "missing_files": []}


def test_minimax_ready_when_all_files_exist(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    for rel in REQUIRED_FILES["minimax"]:
        _touch(models, rel)
    result = check_model("minimax", models)
    assert result["ready"] is True
    assert result["missing_files"] == []


def test_minimax_not_ready_when_video_vae_missing(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    for rel in REQUIRED_FILES["minimax"]:
        if rel.endswith("minimax_h3_video_vae_fp16.safetensors"):
            continue
        _touch(models, rel)
    result = check_model("minimax", models)
    assert result["ready"] is False
    assert "vae/minimax_h3_video_vae_fp16.safetensors" in result["missing_files"]


def test_flux_ready_when_t5_under_clip(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    for rel in REQUIRED_FILES["flux"]:
        if rel == "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf":
            _touch(models, "clip/t5-v1_1-xxl-encoder-Q4_K_S.gguf")
        else:
            _touch(models, rel)
    result = check_model("flux", models)
    assert result["ready"] is True
    assert result["missing_files"] == []


def test_unknown_model_returns_not_ready(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    models.mkdir(parents=True)
    result = check_model("nonexistent", models)
    assert result["ready"] is False
    assert result["missing_files"] == ["unknown model: nonexistent"]


def test_face_identity_readiness_reports_missing_files(tmp_path: Path):
    result = check_face_identity_models(tmp_path / "face" / "models")
    assert result["ready"] is False
    assert result["reason"] == "face_model_files_missing"
    assert set(result["missing_files"]) == {
        "face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx",
    }


def test_face_identity_readiness_fingerprints_existing_files(tmp_path: Path):
    models = tmp_path / "face" / "models"
    _touch(models, "face_detection_yunet_2023mar.onnx")
    _touch(models, "face_recognition_sface_2021dec.onnx")
    entries = {}
    for name in (
        "face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx",
    ):
        payload = (models / name).read_bytes()
        entries[name] = {
            "url": f"https://example.invalid/{name}",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    (models / "manifest.json").write_text(
        json.dumps({"models": entries}), encoding="utf-8"
    )
    result = check_face_identity_models(models)
    assert result["ready"] is True
    assert result["reason"] == ""
    assert set(result["fingerprints"]) == {
        "face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx",
    }


def test_face_identity_readiness_rejects_missing_manifest(tmp_path: Path):
    models = tmp_path / "face" / "models"
    _touch(models, "face_detection_yunet_2023mar.onnx")
    _touch(models, "face_recognition_sface_2021dec.onnx")
    result = check_face_identity_models(models)
    assert result["ready"] is False
    assert result["reason"] == "face_model_manifest_missing"


def test_face_identity_readiness_rejects_corrupted_installed_model(tmp_path: Path):
    models = tmp_path / "face" / "models"
    names = (
        "face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx",
    )
    entries = {}
    for name in names:
        _touch(models, name)
        payload = (models / name).read_bytes()
        entries[name] = {
            "url": f"https://example.invalid/{name}",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    (models / "manifest.json").write_text(
        json.dumps({"models": entries}), encoding="utf-8"
    )
    (models / names[0]).write_bytes(b"corrupted")

    result = check_face_identity_models(models)

    assert result["ready"] is False
    assert result["reason"] == "face_model_hash_mismatch"
    assert result["invalid_files"] == [names[0]]
