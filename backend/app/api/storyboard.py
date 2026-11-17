# ============================================
# 分镜故事板 API
# ============================================
# 提供分镜生成、管理、一致性检测等接口
# ============================================

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.services.prompt_compose import (
    collect_lock_ens,
    compose_still_prompt,
    resolve_i2v_prompt,
)
from app.services.model_readiness import check_model
from app.services.runtime import client, job_queue, job_repo, queue, store, storyboard_store
from app.services.workflows import SUPPORTED_MODELS
from app.services.workflows.minimax import (
    DEFAULT_HEIGHT,
    DEFAULT_LENGTH,
    DEFAULT_WIDTH,
)
from app.api.prompt_architecture import get_h3_compiler
from app.db.repositories.compiled_prompts import CompiledPromptRepository
from app.services.h3_compiler import canonical_source_hash
from app.services.llm_provider import LLMError
from app.api.storyboard_render import (
    get_storyboard_render_module,
    raise_render_http_error,
)
from app.services.storyboard_render.types import RenderPolicy, StoryboardRenderError
from app.services.runtime import render_attempt_repo

router = APIRouter()


def resolve_frame_prompt_en(frame: dict) -> str:
    """出图用英文提示词：prompt_en → description_en → 由镜头字段拼装。"""
    for key in ("prompt_en", "description_en"):
        value = (frame.get(key) or "").strip()
        if value:
            return value
    parts: list[str] = []
    shot = (frame.get("shot_type") or "").strip()
    scene = (frame.get("scene") or "").strip()
    desc = (frame.get("description") or "").strip()
    if shot:
        parts.append(f"{shot} shot")
    if scene:
        parts.append(f"scene: {scene}")
    if desc:
        parts.append(desc)
    return ", ".join(parts)


def _locks_for_frame(project_id: str, frame: dict) -> list[str]:
    assets = store.list(project_id)
    names = [n.strip() for n in str(frame.get("character") or "").split(",") if n.strip()]
    locks: list[str] = []
    seen: set[str] = set()
    for name in names:
        for lock in collect_lock_ens(assets, character_name=name, scene_name=""):
            if lock not in seen:
                seen.add(lock)
                locks.append(lock)
    scene_name = (frame.get("scene") or "").strip()
    for lock in collect_lock_ens(assets, character_name="", scene_name=scene_name):
        if lock not in seen:
            seen.add(lock)
            locks.append(lock)
    return locks


def _assert_frame_characters_ready(project_id: str, frame: dict) -> None:
    from app.services.asset_readiness import unready_character_names

    names = [n.strip() for n in str(frame.get("character") or "").split(",") if n.strip()]
    if not names:
        return
    unready = unready_character_names(store.list(project_id), names)
    if unready:
        joined = "、".join(unready)
        raise HTTPException(
            status_code=400,
            detail=(
                f"characters_not_ready: {joined} — 请先在资产生成完成定妆图与身份锁"
            ),
        )

# ============================================
# 数据模型
# ============================================

class StoryboardFrame(BaseModel):
    """分镜帧模型"""
    id: str
    number: int
    description: str = ""
    description_en: str = ""
    character: str = ""
    scene: str = ""
    scene_id: Optional[str] = None
    shot_type: str = "中景"
    angle: str = "平视"
    movement: str = "固定"
    duration: float = 3.0
    prompt_cn: str = ""
    prompt_en: str = ""
    motion_prompt_en: str = ""
    status: str = "pending"
    image_url: Optional[str] = None
    negative_prompt: Optional[str] = None
    asset_id: Optional[str] = None
    error: Optional[str] = None
    model: Optional[str] = None
    video_url: Optional[str] = None
    video_status: Optional[str] = None
    video_error: Optional[str] = None
    video_job_id: Optional[str] = None
    accepted_render_attempt_id: Optional[str] = None
    lines: List[dict] = Field(default_factory=list)


class GenerateFrameRequest(BaseModel):
    """单帧出图请求"""
    model: Optional[str] = None
    aspect: Optional[str] = None  # square/portrait/landscape


class GenerateFrameVideoRequest(BaseModel):
    """分镜帧图生视频"""
    width: Optional[int] = None
    height: Optional[int] = None
    length: Optional[int] = None
    seed: Optional[int] = None
    model: Optional[str] = "minimax"
    compiled_prompt_id: Optional[str] = None
    auto_compile: bool = True


class FrameUpdateRequest(BaseModel):
    """分镜帧更新请求"""
    description: Optional[str] = None
    description_en: Optional[str] = None
    prompt_cn: Optional[str] = None
    prompt_en: Optional[str] = None
    motion_prompt_en: Optional[str] = None
    negative_prompt: Optional[str] = None
    shot_type: Optional[str] = None
    angle: Optional[str] = None
    movement: Optional[str] = None
    character: Optional[str] = None
    scene: Optional[str] = None
    duration: Optional[int] = None
    model: Optional[str] = None


class CreateFrameRequest(BaseModel):
    """新增分镜帧请求"""
    description: Optional[str] = ""
    description_en: Optional[str] = ""
    character: Optional[str] = ""
    scene: Optional[str] = ""
    scene_id: Optional[str] = None


class ConsistencyCheckResult(BaseModel):
    """一致性检测结果"""
    frame_id: str
    issue: str
    severity: str           # info / warning / error
    suggestion: str


# ============================================
# 辅助
# ============================================

_UPDATABLE_FIELDS = (
    "description",
    "description_en",
    "prompt_cn",
    "prompt_en",
    "motion_prompt_en",
    "negative_prompt",
    "shot_type",
    "angle",
    "movement",
    "character",
    "scene",
    "duration",
    "model",
)


def _sync_from_asset(project_id: str, frame: dict) -> dict:
    """若帧已关联资产，则同步 status / image_url / error。"""
    asset_id = frame.get("asset_id")
    if not asset_id:
        return frame
    asset = store.get(project_id, asset_id)
    if not asset:
        return frame
    updated = storyboard_store.update(
        project_id,
        frame["id"],
        status=asset.get("status", frame.get("status")),
        image_url=asset.get("image_url"),
        error=asset.get("error"),
    )
    return updated


# ============================================
# API 接口
# ============================================

@router.get("/{project_id}/frames", response_model=List[StoryboardFrame], summary="获取分镜列表")
async def get_frames(project_id: str, scene_id: Optional[str] = None):
    """
    获取分镜列表

    - **project_id**: 项目 ID
    - **scene_id**: 场景 ID（可选，按场景筛选）
    """
    frames = storyboard_store.list(project_id)
    if scene_id:
        frames = [
            f
            for f in frames
            if f.get("scene_id") == scene_id or f.get("scene") == scene_id
        ]
    return [_sync_from_asset(project_id, f) for f in frames]


@router.post("/{project_id}/frames", response_model=StoryboardFrame, summary="新增分镜帧")
async def create_frame(
    project_id: str, request: CreateFrameRequest = CreateFrameRequest()
):
    """新增一个分镜帧；未填场景时追加到列表末尾。"""
    frame = storyboard_store.create(
        project_id,
        description=request.description or "",
        description_en=request.description_en or "",
        character=request.character or "",
        scene=request.scene or "",
        scene_id=request.scene_id,
        status="pending",
    )
    return _sync_from_asset(project_id, frame)


@router.delete("/{project_id}/frames/{frame_id}", summary="删除分镜帧")
async def delete_frame(project_id: str, frame_id: str):
    """删除单个分镜帧。"""
    storyboard_store.delete(project_id, frame_id)
    return {"message": "删除成功"}


@router.get("/{project_id}/frames/{frame_id}", response_model=StoryboardFrame, summary="获取分镜详情")
async def get_frame(project_id: str, frame_id: str):
    """获取分镜详情"""
    frame = storyboard_store.get(project_id, frame_id)
    if not frame:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return _sync_from_asset(project_id, frame)


@router.put("/{project_id}/frames/{frame_id}", response_model=StoryboardFrame, summary="更新分镜帧")
async def update_frame(project_id: str, frame_id: str, request: FrameUpdateRequest):
    """更新分镜帧字段"""
    frame = storyboard_store.get(project_id, frame_id)
    if not frame:
        raise HTTPException(status_code=404, detail="分镜不存在")
    fields = {
        k: v
        for k, v in request.model_dump(exclude_unset=True).items()
        if k in _UPDATABLE_FIELDS and v is not None
    }
    if not fields:
        return frame
    return storyboard_store.update(project_id, frame_id, **fields)


@router.post(
    "/{project_id}/frames/{frame_id}/generate",
    response_model=StoryboardFrame,
    summary="生成分镜图",
)
async def generate_frame_image(project_id: str, frame_id: str, request: GenerateFrameRequest = GenerateFrameRequest()):
    """
    为指定分镜帧出图：创建 asset 并入队 AssetQueue。
    """
    if not storyboard_store.get(project_id, frame_id):
        raise HTTPException(status_code=404, detail="分镜不存在")
    if request.model and request.model != "flux":
        raise HTTPException(status_code=400, detail="formal storyboard render uses flux_kontext")
    try:
        get_storyboard_render_module().submit(
            project_id,
            frame_id,
            policy=RenderPolicy(),
        )
    except StoryboardRenderError as exc:
        raise_render_http_error(exc)
    updated = storyboard_store.get(project_id, frame_id)
    assert updated is not None
    return updated


@router.post(
    "/{project_id}/frames/{frame_id}/generate-video",
    response_model=StoryboardFrame,
    summary="分镜帧图生视频（MiniMax）",
)
async def generate_frame_video(
    project_id: str,
    frame_id: str,
    request: GenerateFrameVideoRequest = GenerateFrameVideoRequest(),
):
    frame = storyboard_store.get(project_id, frame_id)
    if not frame:
        raise HTTPException(status_code=404, detail="分镜不存在")
    image_url = (frame.get("image_url") or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="frame image required")
    attempts = render_attempt_repo.list_for_frame(project_id, frame_id)
    accepted_id = frame.get("accepted_render_attempt_id")
    legacy_accepted_frame = False
    if accepted_id:
        accepted = render_attempt_repo.get(accepted_id)
        if (
            not accepted
            or accepted.get("project_id") != project_id
            or accepted.get("frame_id") != frame_id
            or accepted.get("status") != "accepted"
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "accepted_frame_required",
                    "message": "当前分镜没有有效的已接受候选图",
                },
            )
    elif frame.get("status") == "completed" and not attempts:
        legacy_accepted_frame = True
    else:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "accepted_frame_required",
                "message": "请先审核并接受一张分镜候选图，再生成 H3 视频",
            },
        )

    model = (request.model or "minimax").lower()
    if model != "minimax":
        raise HTTPException(status_code=400, detail="only model=minimax supported")
    ready = check_model("minimax", settings.comfyui_models_dir)
    if not ready["ready"]:
        missing = ", ".join(ready["missing_files"])
        raise HTTPException(
            status_code=400,
            detail=f"model not ready: minimax; missing: {missing}",
        )
    if not client.health():
        raise HTTPException(status_code=503, detail="comfyui_unavailable")

    from app.services.render_compose import _resolve_image_path

    img_path = _resolve_image_path(image_url, settings.media_mount_dir)
    if not img_path.is_file():
        raise HTTPException(status_code=400, detail=f"frame image file missing: {image_url}")

    length = request.length or DEFAULT_LENGTH
    duration_sec = round(length / 24.0, 2)
    compiler = get_h3_compiler()
    try:
        if request.compiled_prompt_id:
            artifact = CompiledPromptRepository().get(request.compiled_prompt_id)
            if not artifact:
                raise HTTPException(status_code=404, detail="compiled prompt not found")
            if (
                artifact.get("project_id") != project_id
                or artifact.get("source_type") != "frame"
                or artifact.get("source_id") != frame_id
                or artifact.get("mode") != "i2va"
            ):
                raise HTTPException(status_code=409, detail="compiled prompt source mismatch")
            current_hash = canonical_source_hash(
                compiler.frame_context(project_id, frame_id, duration_sec=duration_sec)
            )
            artifact["stale"] = artifact.get("source_hash") != current_hash
        elif request.auto_compile:
            artifact = compiler.compile_frame(
                project_id, frame_id, mode="i2va", duration_sec=duration_sec
            )
        else:
            raise HTTPException(status_code=409, detail="fresh H3 compilation required")
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"compile source missing: {exc.args[0]}") from exc
    if artifact.get("stale"):
        raise HTTPException(status_code=409, detail="compiled prompt is stale")
    validation = artifact.get("validation_json") or {}
    if not validation.get("valid"):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_h3_prompt", "issues": validation.get("issues") or []},
        )
    prompt_en = str(artifact.get("content") or "").strip()
    if not prompt_en:
        raise HTTPException(status_code=422, detail="compiled H3 prompt is empty")

    job = job_repo.create(
        type="video_generate",
        project_id=project_id,
        title=f"分镜视频 · {frame_id}",
        payload={
            "prompt_en": prompt_en,
            "compiled_prompt_id": artifact["id"],
            "guide_version": artifact.get("guide_version") or "",
            "mode": "i2v",
            "frame_id": frame_id,
            "first_frame_path": str(img_path),
            "width": request.width or DEFAULT_WIDTH,
            "height": request.height or DEFAULT_HEIGHT,
            "length": length,
            "seed": request.seed,
            "legacy_accepted_frame": legacy_accepted_frame,
        },
        link_path=f"/workbench/{project_id}/storyboard",
    )
    job_queue.enqueue(job["id"])
    return storyboard_store.update(
        project_id,
        frame_id,
        video_status="generating",
        video_error=None,
        video_job_id=job["id"],
    )


@router.post("/{project_id}/generate", response_model=StoryboardFrame, summary="生成分镜")
async def generate_frame(project_id: str):
    """生成新分镜帧（占位，经 store 创建）"""
    return storyboard_store.create(
        project_id,
        description="新分镜",
        description_en="New Frame",
        status="generating",
    )


@router.post("/{project_id}/consistency-check", response_model=List[ConsistencyCheckResult], summary="一致性检测")
async def consistency_check(project_id: str):
    """基于分镜元数据的启发式一致性检测（非像素视觉比对）。"""
    from app.services.storyboard_consistency import check_storyboard_consistency

    frames = storyboard_store.list(project_id)
    return check_storyboard_consistency(frames)
