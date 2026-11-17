# ============================================
# 剧本工坊 API
# ============================================

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.repositories.projects import ProjectRepository
from app.db.repositories.scenes import SceneRepository
from app.services.llm_runtime import build_llm_provider
from app.services.script_expand import ScriptExpandError, ScriptExpandService

router = APIRouter()
_scene_repo = SceneRepository()
_project_repo = ProjectRepository()


class Scene(BaseModel):
    id: str
    number: int
    name: str = ""
    location: str = ""
    time: str = ""
    characters: List[str] = Field(default_factory=list)
    props: List[str] = Field(default_factory=list)
    look_states: dict[str, dict[str, str]] = Field(default_factory=dict)
    dialogue_count: int = 0
    narration_count: int = 0
    description: str = ""
    description_en: str = ""
    prompt_cn: str = ""
    prompt_en: str = ""
    negative_prompt: str = ""
    interpretation_cn: str = ""
    lines: List[dict] = Field(default_factory=list)


class SceneUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    time: Optional[str] = None
    characters: Optional[List[str]] = None
    props: Optional[List[str]] = None
    look_states: Optional[dict[str, dict[str, str]]] = None
    description: Optional[str] = None
    description_en: Optional[str] = None
    prompt_cn: Optional[str] = None
    prompt_en: Optional[str] = None
    negative_prompt: Optional[str] = None
    interpretation_cn: Optional[str] = None
    dialogue_count: Optional[int] = None
    narration_count: Optional[int] = None
    lines: Optional[List[dict]] = None


class ScriptAnalysisRequest(BaseModel):
    text: str
    style: Optional[str] = None
    project_id: str


class ScriptExpandRequest(BaseModel):
    project_id: str
    text: str
    style: Optional[str] = None


class ScriptAnalysisResponse(BaseModel):
    scene_count: int
    character_count: int
    prop_count: int
    scenes: List[Scene]


class SuggestionItem(BaseModel):
    issue: str
    severity: str = "info"
    suggestion: str = ""


class ScriptSuggestResponse(BaseModel):
    suggestions: List[SuggestionItem]
    provider: str = "rule"
    scene_count: int = 0


def _expand_service() -> ScriptExpandService:
    return ScriptExpandService(llm=build_llm_provider())


def _persist_scenes(project_id: str, scenes: list[dict]) -> list[dict]:
    return _scene_repo.replace_all(project_id, scenes)


def _stats(scenes: list[dict]) -> dict:
    chars = set()
    props = set()
    for s in scenes:
        chars.update(s.get("characters") or [])
        props.update(s.get("props") or [])
    return {
        "scene_count": len(scenes),
        "character_count": len(chars),
        "prop_count": len(props),
        "scenes": scenes,
    }


def run_expand_persist(project_id: str, text: str, style: str = "") -> dict:
    raw_scenes = _expand_service().expand(text=text, style=style or "", mode="expand")
    scenes = _persist_scenes(project_id, raw_scenes)
    return _stats(scenes)


def run_analyze_persist(project_id: str, text: str, style: str = "") -> dict:
    raw_scenes = _expand_service().expand(text=text, style=style or "", mode="analyze")
    scenes = _persist_scenes(project_id, raw_scenes)
    return _stats(scenes)


@router.post("/expand", response_model=ScriptAnalysisResponse, summary="AI 扩写剧本")
async def expand_script(request: ScriptExpandRequest):
    if not _project_repo.get(request.project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    if not (request.text or "").strip():
        raise HTTPException(status_code=400, detail="text 不能为空")
    try:
        return run_expand_persist(
            request.project_id, request.text, request.style or ""
        )
    except ScriptExpandError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/analyze", response_model=ScriptAnalysisResponse, summary="解析剧本")
async def analyze_script(request: ScriptAnalysisRequest):
    if not _project_repo.get(request.project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    if not (request.text or "").strip():
        raise HTTPException(status_code=400, detail="text 不能为空")
    try:
        return run_analyze_persist(
            request.project_id, request.text, request.style or ""
        )
    except ScriptExpandError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/{project_id}/scenes", response_model=List[Scene], summary="获取场景列表")
async def get_scenes(project_id: str):
    return _scene_repo.list_by_project(project_id)


@router.get("/{project_id}/scenes/{scene_id}", response_model=Scene, summary="获取场景详情")
async def get_scene(project_id: str, scene_id: str):
    scene = _scene_repo.get(project_id, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    return scene


@router.put("/{project_id}/scenes/{scene_id}", response_model=Scene, summary="更新场景")
async def update_scene(project_id: str, scene_id: str, body: SceneUpdate):
    try:
        return _scene_repo.update(
            project_id, scene_id, **body.model_dump(exclude_unset=True)
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="场景不存在") from None


@router.post(
    "/{project_id}/suggest",
    response_model=ScriptSuggestResponse,
    summary="剧本智能建议",
)
async def script_suggest(project_id: str):
    """基于已落库场景生成创作建议（LLM 增强 + 规则兜底）。"""
    scenes = _scene_repo.list_by_project(project_id)
    from app.services.script_suggest import ScriptSuggestService

    provider = "rule"
    try:
        svc = ScriptSuggestService(llm=build_llm_provider())
        suggestions = svc.suggest(scenes)
        provider = "llm"
    except Exception:
        suggestions = ScriptSuggestService(llm=None).suggest(scenes)
        provider = "rule"
    return ScriptSuggestResponse(
        suggestions=suggestions,
        provider=provider,
        scene_count=len(scenes),
    )
