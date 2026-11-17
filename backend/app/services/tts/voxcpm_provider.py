from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from app.core.settings import settings


class VoxCPMNotReady(RuntimeError):
    pass


def resolve_voxcpm_dir(model_dir: Path | None = None) -> Path:
    if model_dir is not None:
        return Path(model_dir)
    env = os.environ.get("VOXCPM_MODEL_DIR")
    if env:
        return Path(env)
    return settings.modelhub_root / "tts" / "VoxCPM2"


class VoxCPMProvider:
    _model: Any = None

    def __init__(self, model_dir: Path | None = None, **_kwargs) -> None:
        self.model_dir = resolve_voxcpm_dir(model_dir)

    def _ensure_model(self):
        if VoxCPMProvider._model is not None:
            return VoxCPMProvider._model
        if not self.model_dir.exists():
            raise VoxCPMNotReady(
                f"VoxCPM 权重目录不存在: {self.model_dir}（可设 VOXCPM_MODEL_DIR 或 MODELHUB_ROOT/tts/VoxCPM2）"
            )
        try:
            from voxcpm import VoxCPM  # type: ignore
        except ImportError as e:
            raise VoxCPMNotReady(
                "未安装 voxcpm 包，无法使用 VoxCPM 引擎"
            ) from e
        VoxCPMProvider._model = VoxCPM.from_pretrained(
            str(self.model_dir), load_denoiser=False
        )
        return VoxCPMProvider._model

    def synthesize(self, *, text: str, emotion: str = "", speaker: str = "") -> bytes:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty tts text")
        if emotion:
            text = f"（{emotion}）{text}"
        model = self._ensure_model()
        # Library APIs vary; prefer generate → wav bytes / path
        if hasattr(model, "generate"):
            out = model.generate(text)
        elif hasattr(model, "synthesize"):
            out = model.synthesize(text)
        else:
            raise VoxCPMNotReady("VoxCPM 模型无 generate/synthesize 方法")
        if isinstance(out, (bytes, bytearray)):
            return bytes(out)
        if isinstance(out, str) and Path(out).exists():
            return Path(out).read_bytes()
        if isinstance(out, Path) and out.exists():
            return out.read_bytes()
        raise VoxCPMNotReady(f"无法解析 VoxCPM 输出类型: {type(out)}")
