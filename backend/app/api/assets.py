# ============================================
# 资产生成 API
# ============================================
# 提供角色、场景、道具等图像资产生成接口
# ============================================

from fastapi import APIRouter, HTTPException
from typing import List, Optional
import uuid
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.db.repositories.projects import ProjectRepository
from app.db.repositories.scenes import SceneRepository
from app.services.asset_script_sync import sync_from_script
from app.services.model_readiness import check_model
from app.services.runtime import client, job_repo, queue, store
from app.services.workflows import SUPPORTED_MODELS
from app.services.casting import CASTING_NEGATIVE_PROMPT, CastingService
from app.services.llm_runtime import build_llm_provider
from app.services.visual_bible import VisualBibleService

router = APIRouter()

# ============================================
# 数据模型
# ============================================

class Asset(BaseModel):
    """资产模型"""
    id: str
    name: str
    name_en: str
    type: str                  # character / scene / prop
    status: str                # completed / generating / pending / failed
    prompt_cn: str             # 中文提示词
    prompt_en: str             # 英文提示词
    image_url: Optional[str] = None  # 生成的图片 URL
    created_at: str
    error: Optional[str] = None
    model: Optional[str] = None
    negative_prompt: Optional[str] = None
    lock_en: str = ""
    aspect: Optional[str] = None
    candidate_group_id: Optional[str] = None
    candidate_index: Optional[int] = None
    selection_status: str = "legacy"
    identity: dict = Field(default_factory=dict)


class AssetGenerateRequest(BaseModel):
    """资产生成请求"""
    name: str
    type: str
    prompt_cn: str
    prompt_en: str
    template_id: Optional[str] = None
    model: Optional[str] = "flux"
    negative_prompt: Optional[str] = None
    lock_en: Optional[str] = None
    asset_id: Optional[str] = None  # 传入则覆盖该资产再出图，不新建同名条目
    aspect: Optional[str] = None  # square/portrait/landscape


class SyncFromScriptRequest(BaseModel):
    types: list[str] = Field(default_factory=lambda: ["character", "scene"])
    # 默认走高质量 LLM 润色（character_lock / scene_lock）；sync 内部并发且失败降级粗模板。
    enrich: bool = True


def get_casting_service() -> CastingService:
    return CastingService(
        llm=build_llm_provider(),
        visual_bible=VisualBibleService(),
    )


def _assert_flux_ready() -> None:
    ready = check_model("flux", settings.comfyui_models_dir)
    if not ready["ready"]:
        missing = ", ".join(ready["missing_files"])
        raise HTTPException(
            status_code=400,
            detail=f"model not ready: flux; missing: {missing}",
        )
    if not client.health():
        raise HTTPException(status_code=503, detail="comfyui_unavailable")


def _enqueue_asset(project_id: str, asset: dict) -> None:
    from datetime import datetime

    job = job_repo.create(
        type="asset_generate",
        project_id=project_id,
        title=f"资产生成 · {asset['name']} · 选角{asset.get('candidate_index') or ''}",
        payload={"asset_id": asset["id"]},
        link_path=f"/workbench/{project_id}/assets",
    )
    job_repo.update(
        job["id"],
        status="running",
        progress=10,
        started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    queue.enqueue(project_id, asset["id"])


# ============================================
# API 接口
# ============================================

def _list_assets(project_id: str, asset_type: str | None = None) -> list[dict]:
    """返回 store 中的真实资产，可按 type 过滤。"""
    items = store.list(project_id)
    if asset_type:
        items = [i for i in items if i["type"] == asset_type]
    return items


@router.get("/{project_id}/assets", response_model=List[Asset], summary="获取项目资产列表")
async def get_project_assets(project_id: str, type: Optional[str] = None):
    """获取项目的全部资产生成，可按 type 过滤（character/scene/prop）。"""
    return _list_assets(project_id, type)


@router.get("/{project_id}/characters", response_model=List[Asset], summary="获取角色列表")
async def get_characters(project_id: str):
    """获取项目的角色资产列表"""
    return _list_assets(project_id, "character")


@router.get("/{project_id}/scenes", response_model=List[Asset], summary="获取场景列表")
async def get_scene_assets(project_id: str):
    """获取项目的场景资产列表"""
    return _list_assets(project_id, "scene")


@router.get("/{project_id}/props", response_model=List[Asset], summary="获取道具列表")
async def get_props(project_id: str):
    """获取项目的道具资产列表"""
    return _list_assets(project_id, "prop")


@router.post("/{project_id}/generate", response_model=Asset, summary="生成资产")
async def generate_asset(project_id: str, request: AssetGenerateRequest):
    """
    生成新资产（角色/场景/道具）
    
    - **name**: 资产名称
    - **type**: 资产类型（character/scene/prop）
    - **prompt_cn**: 中文提示词
    - **prompt_en**: 英文提示词
    - **model**: 出图模型（flux，默认 flux）
    """
    model = request.model or "flux"
    if model not in SUPPORTED_MODELS:
        raise HTTPException(status_code=400, detail=f"unknown model: {model}")
    # 双保险：前端应已禁用未就绪模型；此处再拦一层避免白跑队列
    ready = check_model(model, settings.comfyui_models_dir)
    if not ready["ready"]:
        missing = ", ".join(ready["missing_files"])
        raise HTTPException(
            status_code=400,
            detail=f"model not ready: {model}; missing: {missing}",
        )
    if not client.health():
        raise HTTPException(status_code=503, detail="comfyui_unavailable")
    from app.services.prompt_templates import get_template, template_for_asset_type

    tpl = None
    if request.template_id:
        tpl = get_template(request.template_id)
    if tpl is None:
        tpl = template_for_asset_type(request.type)
    negative = (request.negative_prompt or "").strip()
    if not negative and tpl:
        negative = str(tpl.get("negative_prompt_en") or "")
    if request.asset_id:
        existing = store.get(project_id, request.asset_id)
        if not existing:
            raise HTTPException(status_code=404, detail="资产不存在")
        if existing.get("status") == "generating":
            raise HTTPException(status_code=409, detail="asset_generating")
        asset = store.update(
            project_id,
            request.asset_id,
            name=request.name,
            type=request.type,
            prompt_cn=request.prompt_cn,
            prompt_en=request.prompt_en,
            model=model,
            negative_prompt=negative,
            lock_en=request.lock_en or "",
            aspect=request.aspect or "square",
            status="generating",
            error=None,
        )
    else:
        asset = store.create(
            project_id=project_id,
            name=request.name,
            type=request.type,
            prompt_cn=request.prompt_cn,
            prompt_en=request.prompt_en,
            model=model,
            negative_prompt=negative,
            lock_en=request.lock_en or "",
            aspect=request.aspect or "square",
        )
    from datetime import datetime

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    job = job_repo.create(
        type="asset_generate",
        project_id=project_id,
        title=f"资产生成 · {request.name}",
        payload={"asset_id": asset["id"]},
        link_path=f"/workbench/{project_id}/assets",
    )
    job_repo.update(job["id"], status="running", progress=10, started_at=now)
    queue.enqueue(project_id, asset["id"])
    return asset


@router.post(
    "/{project_id}/characters/{asset_id}/cast",
    summary="生成四版 AI 选角候选",
)
def cast_character(project_id: str, asset_id: str):
    source = store.get(project_id, asset_id)
    if not source or source.get("type") != "character":
        raise HTTPException(status_code=404, detail="角色资产不存在")
    _assert_flux_ready()
    brief = " | ".join(
        part
        for part in (
            str(source.get("prompt_cn") or "").strip(),
            str(source.get("prompt_en") or "").strip(),
            str(source.get("lock_en") or "").strip(),
        )
        if part
    )
    concepts = get_casting_service().generate(
        project_id=project_id,
        name=str(source.get("name") or "角色"),
        brief=brief,
    )
    is_recast = bool(source.get("candidate_group_id"))
    group_id = f"cast_{uuid.uuid4().hex[:12]}"
    existing: dict[int, dict] = {}
    if not is_recast:
        existing[1] = source
    negative = CASTING_NEGATIVE_PROMPT
    candidates: list[dict] = []
    for index, concept in enumerate(concepts, start=1):
        fields = {
            "name": source["name"],
            "type": "character",
            "prompt_cn": concept.label,
            "prompt_en": concept.prompt_en,
            "model": "flux",
            "negative_prompt": negative,
            "lock_en": concept.identity_anchor,
            "aspect": "portrait",
            "candidate_group_id": group_id,
            "candidate_index": index,
            "selection_status": "candidate",
            "identity": {
                "identity_anchor": concept.identity_anchor,
                "stable_traits": [
                    "facial_geometry",
                    "age_impression",
                    "stable_hairstyle",
                    "body_build",
                ],
                "source": "casting_v1",
            },
            "status": "generating",
            "image_url": None,
            "error": None,
        }
        current = existing.get(index)
        if current:
            candidate = store.update(project_id, current["id"], **fields)
        else:
            create_fields = {
                key: value
                for key, value in fields.items()
                if key not in {"image_url", "error"}
            }
            candidate = store.create(project_id=project_id, **create_fields)
        candidates.append(candidate)
        _enqueue_asset(project_id, candidate)
    return {"candidate_group_id": group_id, "candidates": candidates}


@router.post(
    "/{project_id}/characters/{asset_id}/select",
    response_model=Asset,
    summary="选定角色定妆候选",
)
def select_character_candidate(project_id: str, asset_id: str):
    candidate = store.get(project_id, asset_id)
    if not candidate or candidate.get("type") != "character":
        raise HTTPException(status_code=404, detail="角色候选不存在")
    if not candidate.get("candidate_group_id"):
        raise HTTPException(status_code=400, detail="not_casting_candidate")
    if candidate.get("status") != "completed" or not candidate.get("image_url"):
        raise HTTPException(status_code=409, detail="candidate_not_completed")
    selected = None
    candidate_name = str(candidate.get("name") or "").strip()
    for sibling in store.list(project_id):
        if sibling.get("type") != "character":
            continue
        if str(sibling.get("name") or "").strip() != candidate_name:
            continue
        if not sibling.get("candidate_group_id"):
            continue
        status = "selected" if sibling["id"] == asset_id else "rejected"
        updated = store.update(
            project_id,
            sibling["id"],
            selection_status=status,
        )
        if sibling["id"] == asset_id:
            selected = updated
    if selected is None:
        raise HTTPException(status_code=404, detail="角色候选不存在")
    return selected


@router.post("/{project_id}/sync-from-script", summary="从剧本同步角色/场景资产草稿")
def sync_assets_from_script(
    project_id: str, body: SyncFromScriptRequest = SyncFromScriptRequest()
):
    project = ProjectRepository().get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    scenes = SceneRepository().list_by_project(project_id)
    if not scenes:
        raise HTTPException(status_code=400, detail="请先在剧本工坊完成扩写/解析。")
    allowed = tuple(t for t in body.types if t in ("character", "scene"))
    polish = None
    if body.enrich:
        try:
            from app.api.prompts import get_polish_service

            polish = get_polish_service()
        except Exception:
            polish = None
    try:
        return sync_from_script(
            project=project,
            scenes=scenes,
            store=store,
            types=allowed or ("character", "scene"),
            enrich=body.enrich,
            polish_svc=polish,
        )
    except ValueError as e:
        if str(e) == "no_scenes":
            raise HTTPException(status_code=400, detail="请先在剧本工坊完成扩写/解析。")
        raise


@router.get("/{project_id}/readiness", summary="角色定妆就绪状态")
def get_asset_readiness(project_id: str):
    from app.services.asset_readiness import character_readiness_report

    return character_readiness_report(_list_assets(project_id))


@router.get("/{project_id}/{asset_id}", response_model=Asset, summary="获取资产详情")
async def get_asset(project_id: str, asset_id: str):
    """获取资产详情"""
    item = store.get(project_id, asset_id)
    if item:
        return item
    raise HTTPException(status_code=404, detail="资产不存在")
