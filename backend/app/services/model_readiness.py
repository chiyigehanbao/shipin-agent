"""Model weight readiness checks for ComfyUI workflows.

Required file paths align with the workflow definitions under
``app/services/workflows/``. Paths are relative to
``{MODELHUB_ROOT}/comfyui/models/`` (see ``Settings.comfyui_models_dir``).

The frontend uses readiness to disable unavailable models; the generate
endpoint performs a second 400 check before dispatching a job.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json

REQUIRED_FILES: dict[str, list[str]] = {
    "flux": [
        "unet/flux1-dev-Q4_K_S.gguf",
        "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
        "clip/clip_l.safetensors",
        "vae/ae.safetensors",
    ],
    "flux_kontext": [
        "unet/flux1-kontext-dev-Q4_K_S.gguf",
        "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
        "clip/clip_l.safetensors",
        "vae/ae.safetensors",
    ],
    "minimax": [
        "diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
        "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "vae/minimax_h3_video_vae_fp16.safetensors",
        "vae/minimax_h3_audio_vae_fp32.safetensors",
    ],
}

# ComfyUI may resolve T5 under text_encoders/ or clip/.
_FILE_CANDIDATES: dict[str, list[str]] = {
    "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf": [
        "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
        "clip/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
    ],
}


def _exists(models_dir: Path, rel: str) -> bool:
    candidates = _FILE_CANDIDATES.get(rel, [rel])
    return any((models_dir / candidate).is_file() for candidate in candidates)


def check_model(model_key: str, models_dir: Path) -> dict:
    required = REQUIRED_FILES.get(model_key)
    if required is None:
        return {
            "ready": False,
            "missing_files": [f"unknown model: {model_key}"],
        }
    missing: list[str] = []
    for rel in required:
        if not _exists(models_dir, rel):
            missing.append(rel)
    return {"ready": len(missing) == 0, "missing_files": missing}


def check_all_models(models_dir: Path) -> dict[str, dict]:
    return {key: check_model(key, models_dir) for key in REQUIRED_FILES}


FACE_IDENTITY_FILES = (
    "face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_face_identity_models(models_dir: Path) -> dict:
    root = Path(models_dir)
    missing = [name for name in FACE_IDENTITY_FILES if not (root / name).is_file()]
    if missing:
        return {
            "ready": False,
            "reason": "face_model_files_missing",
            "missing_files": missing,
            "invalid_files": [],
            "fingerprints": {},
        }
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {
            "ready": False,
            "reason": "face_model_manifest_missing",
            "missing_files": [],
            "invalid_files": [],
            "fingerprints": {},
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest["models"]
        if not isinstance(entries, dict):
            raise ValueError("models must be an object")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {
            "ready": False,
            "reason": "face_model_manifest_invalid",
            "missing_files": [],
            "invalid_files": list(FACE_IDENTITY_FILES),
            "fingerprints": {},
        }
    fingerprints: dict[str, str] = {}
    invalid: list[str] = []
    for name in FACE_IDENTITY_FILES:
        path = root / name
        entry = entries.get(name) or {}
        actual_hash = _sha256(path)
        actual_size = path.stat().st_size
        try:
            expected_size = int(entry.get("size"))
        except (TypeError, ValueError):
            expected_size = -1
        expected_hash = str(entry.get("sha256") or "").lower()
        if actual_size != expected_size or actual_hash.lower() != expected_hash:
            invalid.append(name)
        else:
            fingerprints[name] = f"sha256:{actual_hash}"
    if invalid:
        return {
            "ready": False,
            "reason": "face_model_hash_mismatch",
            "missing_files": [],
            "invalid_files": invalid,
            "fingerprints": fingerprints,
        }
    return {
        "ready": True,
        "reason": "",
        "missing_files": [],
        "invalid_files": [],
        "fingerprints": fingerprints,
    }
