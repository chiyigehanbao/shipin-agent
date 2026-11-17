from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "VisionForge-model-installer/1.0"})
    with urlopen(request, timeout=120) as response, destination.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    prefix = destination.read_bytes()[:256]
    if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise RuntimeError(f"Git LFS pointer downloaded instead of model: {url}")
    if destination.stat().st_size < 1024:
        raise RuntimeError(f"Downloaded model is unexpectedly small: {url}")


def install(target: Path) -> dict:
    root = Path(target).resolve()
    root.mkdir(parents=True, exist_ok=True)
    temporary: dict[str, Path] = {}
    try:
        for name, url in MODELS.items():
            temp = root / f".{name}.{uuid.uuid4().hex}.tmp"
            _download(url, temp)
            temporary[name] = temp
        entries = {
            name: {
                "url": MODELS[name],
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for name, path in temporary.items()
        }
        for name, temp in temporary.items():
            os.replace(temp, root / name)
        manifest = {
            "schema_version": 1,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "models": entries,
        }
        manifest_temp = root / f".manifest.{uuid.uuid4().hex}.tmp"
        manifest_temp.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(manifest_temp, root / "manifest.json")
        return manifest
    finally:
        for temp in temporary.values():
            temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install official OpenCV YuNet and SFace identity models."
    )
    parser.add_argument(
        "--target",
        required=True,
        type=Path,
        help="Explicit destination directory, for example D:\\ModelHub\\face\\models",
    )
    args = parser.parse_args()
    manifest = install(args.target)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
