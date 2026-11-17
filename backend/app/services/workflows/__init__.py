# ============================================
# Workflow 模板与填参
# ============================================
# 节点 ID 约定（Flux，见 flux_gguf.json）：
# 10=UnetLoaderGGUF, 13=DualCLIPLoaderGGUF,
# 14=EmptySD3LatentImage, 15=VAELoader
# ============================================

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

SUPPORTED_MODELS = ("flux",)

_DIR = Path(__file__).resolve().parent

_MODEL_DEFAULTS = {
    "flux": {
        "file": "flux_gguf.json",
        "width": 1024,
        "height": 1024,
    },
}


DEFAULT_NEGATIVE = (
    "anime, illustration, cgi, doll skin, plastic skin, extra fingers, "
    "deformed hands, text, watermark, blurry, lowres"
)

ASPECT_SIZES = {
    "square": (1024, 1024),
    "portrait": (832, 1216),  # 3:4 竖幅，短剧角色定妆/场景
    "landscape": (1216, 832),  # 4:3 横幅
}

DEFAULT_ASPECT = "square"


def resolve_aspect_size(aspect: str | None) -> tuple[int, int]:
    """把资产比例名映射为 (width, height)；未知值回退方形。"""
    key = (aspect or "").strip().lower() or DEFAULT_ASPECT
    return ASPECT_SIZES.get(key, ASPECT_SIZES[DEFAULT_ASPECT])


def build_workflow(
    model: str,
    prompt: str,
    negative_prompt: str = "",
    *,
    steps: int | None = None,
    cfg: float | None = None,
    sampler_name: str | None = None,
    scheduler: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """加载 flux 模板并填入 prompt / negative / 分辨率 / seed / 采样参数。"""
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"unknown model: {model}")
    cfg_model = _MODEL_DEFAULTS[model]
    wf = json.loads((_DIR / cfg_model["file"]).read_text(encoding="utf-8"))
    wf = copy.deepcopy(wf)
    if "6" in wf:
        wf["6"]["inputs"]["text"] = prompt
    neg = (negative_prompt or "").strip() or DEFAULT_NEGATIVE
    if "7" in wf:
        wf["7"]["inputs"]["text"] = neg
    if "3" in wf:
        wf["3"]["inputs"]["seed"] = random.randint(0, 2**31 - 1)
        if steps is not None:
            wf["3"]["inputs"]["steps"] = int(steps)
        if cfg is not None:
            wf["3"]["inputs"]["cfg"] = float(cfg)
        if sampler_name:
            wf["3"]["inputs"]["sampler_name"] = sampler_name
        if scheduler:
            wf["3"]["inputs"]["scheduler"] = scheduler
    if "14" in wf:
        wf["14"]["inputs"]["width"] = width if width is not None else cfg_model["width"]
        wf["14"]["inputs"]["height"] = (
            height if height is not None else cfg_model["height"]
        )
    return wf
