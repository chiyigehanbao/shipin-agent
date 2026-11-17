from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.services.model_readiness import check_model
from app.services.storyboard_render.types import (
    StoryboardRenderError,
    StoryboardRenderRequest,
)
from app.services.workflows import build_workflow


KONTEXT_REQUIRED_NODES = frozenset(
    {
        "LoadImage",
        "FluxKontextImageScale",
        "VAEEncode",
        "ReferenceLatent",
        "FluxGuidance",
        "ConditioningZeroOut",
        "EmptySD3LatentImage",
        "KSampler",
        "UnetLoaderGGUF",
        "DualCLIPLoaderGGUF",
    }
)


class AdapterReadiness(BaseModel):
    ready: bool
    missing_files: list[str] = Field(default_factory=list)
    missing_nodes: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class FluxKontextAdapter:
    name = "flux_kontext"
    workflow_version = "kontext-gguf-v1"
    model_fingerprint = "unet/flux1-kontext-dev-Q4_K_S.gguf"
    _workflow_path = (
        Path(__file__).resolve().parents[1] / "workflows" / "flux_kontext_gguf.json"
    )

    def preflight(
        self,
        *,
        request: StoryboardRenderRequest,
        models_dir: Path,
        available_node_types: set[str],
    ) -> AdapterReadiness:
        count = len(request.character_identities)
        issues = [issue.code for issue in request.validation.issues]
        if count == 0 and "casting_reference_missing" not in issues:
            issues.append("casting_reference_missing")
        if count > 2:
            issues.append("too_many_strong_identities")
        model = check_model("flux_kontext", models_dir)
        missing_nodes = sorted(KONTEXT_REQUIRED_NODES - set(available_node_types))
        return AdapterReadiness(
            ready=(
                request.validation.valid
                and 1 <= count <= 2
                and model["ready"]
                and not missing_nodes
            ),
            missing_files=list(model["missing_files"]),
            missing_nodes=missing_nodes,
            issues=issues,
        )

    def build(
        self,
        *,
        request: StoryboardRenderRequest,
        uploaded_images: list[str],
        seed: int,
    ) -> dict[str, Any]:
        identity_count = len(request.character_identities)
        if identity_count not in (1, 2) or len(uploaded_images) != identity_count:
            raise StoryboardRenderError(
                "reference_upload_invalid",
                "参考图数量必须与一至两个强身份角色严格一致",
                status_code=422,
            )
        workflow = json.loads(self._workflow_path.read_text(encoding="utf-8"))
        workflow = copy.deepcopy(workflow)
        workflow["4"]["inputs"]["image"] = uploaded_images[0]
        workflow["7"]["inputs"]["text"] = request.compiled_prompt
        workflow["3"]["inputs"]["seed"] = int(seed)
        workflow["14"]["inputs"]["width"] = int(request.width)
        workflow["14"]["inputs"]["height"] = int(request.height)
        if identity_count == 2:
            workflow.update(
                {
                    "20": {
                        "class_type": "LoadImage",
                        "inputs": {"image": uploaded_images[1]},
                    },
                    "21": {
                        "class_type": "FluxKontextImageScale",
                        "inputs": {"image": ["20", 0]},
                    },
                    "22": {
                        "class_type": "VAEEncode",
                        "inputs": {"pixels": ["21", 0], "vae": ["15", 0]},
                    },
                    "23": {
                        "class_type": "ReferenceLatent",
                        "inputs": {
                            "conditioning": ["8", 0],
                            "latent": ["22", 0],
                        },
                    },
                }
            )
            workflow["9"]["inputs"]["conditioning"] = ["23", 0]
        return workflow

    @staticmethod
    def parse_result(history: dict[str, Any]) -> dict[str, Any]:
        for output in (history.get("outputs") or {}).values():
            images = output.get("images") or []
            if images:
                return dict(images[0])
        raise StoryboardRenderError(
            "comfyui_unavailable", "ComfyUI 执行结果中没有图片", status_code=502
        )


class TextOnlyFluxAdapter:
    name = "text_only_flux"
    workflow_version = "flux-gguf-v1"
    model_fingerprint = "unet/flux1-dev-Q4_K_S.gguf"

    def preflight(
        self,
        *,
        request: StoryboardRenderRequest,
        models_dir: Path,
        available_node_types: set[str] | None = None,
    ) -> AdapterReadiness:
        model = check_model("flux", models_dir)
        issues = []
        if not request.render_policy.allow_temporary_degradation:
            issues.append("degradation_not_authorized")
        return AdapterReadiness(
            ready=model["ready"] and not issues,
            missing_files=list(model["missing_files"]),
            issues=issues,
        )

    def build(
        self,
        *,
        request: StoryboardRenderRequest,
        uploaded_images: list[str],
        seed: int,
    ) -> dict[str, Any]:
        if not request.render_policy.allow_temporary_degradation:
            raise StoryboardRenderError(
                "degradation_not_authorized",
                "纯文本临时降级必须由用户对本次生成显式授权",
                status_code=409,
            )
        workflow = build_workflow(
            "flux",
            request.compiled_prompt,
            request.negative_prompt,
            width=request.width,
            height=request.height,
        )
        workflow["3"]["inputs"]["seed"] = int(seed)
        return workflow

    @staticmethod
    def parse_result(history: dict[str, Any]) -> dict[str, Any]:
        return FluxKontextAdapter.parse_result(history)
