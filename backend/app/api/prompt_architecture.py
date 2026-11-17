from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.repositories.compiled_prompts import CompiledPromptRepository
from app.services.h3_compiler import H3PromptCompiler
from app.services.h3_validator import validate_h3_prompt
from app.services.llm_provider import LLMError
from app.services.llm_runtime import build_llm_provider
from app.services.prompt_ir import ProjectVisualBible
from app.services.visual_bible import VisualBibleService


router = APIRouter()


class H3CompileRequest(BaseModel):
    project_id: str
    source_type: str = "frame"
    source_id: str
    mode: str = "i2va"
    duration_sec: float = Field(default=5.17, ge=4.0, le=15.0)
    brief: str = ""


class H3UpdateRequest(BaseModel):
    content: str = Field(min_length=1)
    status: str = "draft"
    duration_sec: float = Field(default=5.17, ge=4.0, le=15.0)


def get_h3_compiler() -> H3PromptCompiler:
    return H3PromptCompiler(llm=build_llm_provider())


@router.get("/visual-bible/{project_id}")
def get_visual_bible(project_id: str):
    return VisualBibleService().get(project_id)


@router.put("/visual-bible/{project_id}")
def put_visual_bible(project_id: str, body: ProjectVisualBible):
    VisualBibleService().save(project_id, body)
    return body


@router.post("/h3/compile")
def compile_h3(body: H3CompileRequest):
    compiler = get_h3_compiler()
    try:
        if body.source_type == "frame" and body.mode.lower() == "i2va":
            return compiler.compile_frame(
                body.project_id,
                body.source_id,
                mode="i2va",
                duration_sec=body.duration_sec,
            )
        if body.source_type == "project" and body.mode.lower() == "t2va":
            if not body.brief.strip():
                raise ValueError("brief is required for t2va")
            return compiler.compile_t2va(
                body.project_id,
                body.brief,
                duration_sec=body.duration_sec,
                source_id=body.source_id,
            )
        raise ValueError("phase one supports frame/i2va or project/t2va")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"source not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/h3/latest/{project_id}/{source_type}/{source_id}")
def latest_h3(
    project_id: str,
    source_type: str,
    source_id: str,
    duration_sec: float = 5.17,
):
    if source_type != "frame":
        raise HTTPException(status_code=422, detail="latest phase-one lookup supports frame only")
    try:
        row = get_h3_compiler().latest_frame(
            project_id, source_id, duration_sec=duration_sec
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"source not found: {exc.args[0]}") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="compiled prompt not found")
    return row


@router.put("/h3/{compiled_prompt_id}")
def update_h3(compiled_prompt_id: str, body: H3UpdateRequest):
    if body.status not in {"draft", "locked"}:
        raise HTTPException(status_code=422, detail="status must be draft or locked")
    repo = CompiledPromptRepository()
    row = repo.get(compiled_prompt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="compiled prompt not found")
    report = validate_h3_prompt(
        body.content,
        mode=row["mode"],
        duration_sec=body.duration_sec,
    )
    return repo.update(
        compiled_prompt_id,
        content=body.content.strip(),
        validation_json=report.model_dump(),
        status=body.status,
        is_user_edited=True,
    )
