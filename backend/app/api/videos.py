# ============================================
# MiniMax 视频生成 API（阶段 C：T2V）
# ============================================
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.services.model_readiness import check_model
from app.services.runtime import client, job_queue, job_repo
from app.services.workflows.minimax import (
    DEFAULT_HEIGHT,
    DEFAULT_LENGTH,
    DEFAULT_WIDTH,
)
from app.api.prompt_architecture import get_h3_compiler
from app.services.h3_compiler import canonical_source_hash
from app.services.llm_provider import LLMError

router = APIRouter()


class VideoGenerateRequest(BaseModel):
    prompt_en: str = Field(..., min_length=1)
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    length: int = DEFAULT_LENGTH
    seed: Optional[int] = None
    mode: str = "t2v"
    compiled_prompt_id: Optional[str] = None
    auto_compile: bool = True


@router.post("/{project_id}/generate", summary="MiniMax 文生视频（异步）")
async def generate_video(project_id: str, request: VideoGenerateRequest):
    prompt = (request.prompt_en or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt_en is required")
    mode = (request.mode or "t2v").lower()
    if mode != "t2v":
        raise HTTPException(
            status_code=400,
            detail="only mode=t2v supported here; use storyboard generate-video for i2v",
        )

    ready = check_model("minimax", settings.comfyui_models_dir)
    if not ready["ready"]:
        missing = ", ".join(ready["missing_files"])
        raise HTTPException(
            status_code=400,
            detail=f"model not ready: minimax; missing: {missing}",
        )
    if not client.health():
        raise HTTPException(status_code=503, detail="comfyui_unavailable")

    compiler = get_h3_compiler()
    duration_sec = round(request.length / 24.0, 2)
    if request.compiled_prompt_id:
        from app.db.repositories.compiled_prompts import CompiledPromptRepository

        artifact = CompiledPromptRepository().get(request.compiled_prompt_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="compiled prompt not found")
        if artifact.get("project_id") != project_id or artifact.get("mode") != "t2va":
            raise HTTPException(status_code=409, detail="compiled prompt source mismatch")
        current_hash = canonical_source_hash(
            compiler.t2va_context(project_id, prompt, duration_sec=duration_sec)
        )
        artifact["stale"] = artifact.get("source_hash") != current_hash
    elif request.auto_compile:
        try:
            artifact = compiler.compile_t2va(
                project_id,
                prompt,
                duration_sec=duration_sec,
            )
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=409, detail="fresh H3 compilation required")
    validation = artifact.get("validation_json") or {}
    if artifact.get("stale"):
        raise HTTPException(status_code=409, detail="compiled prompt is stale")
    if not validation.get("valid"):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_h3_prompt", "issues": validation.get("issues") or []},
        )
    compiled_content = str(artifact.get("content") or "").strip()
    if not compiled_content:
        raise HTTPException(status_code=422, detail="compiled H3 prompt is empty")

    job = job_repo.create(
        type="video_generate",
        project_id=project_id,
        title="MiniMax 视频生成",
        payload={
            "prompt_en": compiled_content,
            "compiled_prompt_id": artifact["id"],
            "guide_version": artifact.get("guide_version") or "",
            "mode": mode,
            "width": request.width,
            "height": request.height,
            "length": request.length,
            "seed": request.seed,
        },
        link_path=f"/workbench/{project_id}/storyboard",
    )
    job_queue.enqueue(job["id"])
    return {
        "job_id": job["id"],
        "status": "queued",
        "model": "minimax",
        "mode": mode,
        "compiled_prompt_id": artifact["id"],
    }
