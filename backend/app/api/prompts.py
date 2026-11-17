# ============================================
# 提示词模板 API
# ============================================
# 提供提示词模板的增删改查接口 + 电影感润色
# ============================================

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel, Field

from app.services.cinematic_polish import CinematicPolishService, PolishError
from app.services.llm_provider import LLMError
from app.services.llm_runtime import build_llm_provider

router = APIRouter()

ALLOWED_STAGES = {
    "script_scene",
    "asset",
    "storyboard_frame",
    "character_lock",
    "scene_lock",
    "i2v_motion",
}


class PromptTemplate(BaseModel):
    """提示词模板模型"""
    id: str
    name: str
    name_en: str
    category: str
    category_name: str
    version: str
    usage_count: int
    updated_at: str
    system_prompt_cn: str
    system_prompt_en: str
    user_prompt_cn: str
    user_prompt_en: str
    negative_prompt_cn: Optional[str] = None
    negative_prompt_en: Optional[str] = None
    default_steps: Optional[int] = None
    default_cfg: Optional[float] = None
    default_sampler: Optional[str] = None
    default_scheduler: Optional[str] = None
    default_model: Optional[str] = None


class PolishInput(BaseModel):
    text_cn: str
    text_en: str = ""
    context: dict = Field(default_factory=dict)


class PolishOptions(BaseModel):
    director: Optional[str] = None
    return_interpretation: bool = True


class PolishRequest(BaseModel):
    stage: str
    project_id: str = ""
    input: PolishInput
    options: PolishOptions = PolishOptions()


class PolishResponse(BaseModel):
    interpretation_cn: str = ""
    prompt_en: str = ""
    avoid: str = ""
    prompt_cn: str = ""
    lock_en: str = ""
    motion_prompt_en: str = ""
    provider: str
    pack_version: str


def get_polish_service() -> CinematicPolishService:
    return CinematicPolishService(llm=build_llm_provider())


def run_polish(
    *,
    stage: str,
    text_cn: str,
    text_en: str = "",
    context: dict | None = None,
    return_interpretation: bool = True,
) -> dict:
    if stage not in ALLOWED_STAGES:
        raise ValueError(f"invalid stage: {stage}")
    svc = get_polish_service()
    return svc.polish(
        stage=stage,
        text_cn=text_cn,
        text_en=text_en,
        context=context or {},
        return_interpretation=return_interpretation,
    )


@router.get("", response_model=List[PromptTemplate], summary="获取模板列表")
async def get_templates(category: Optional[str] = None, keyword: Optional[str] = None):
    from app.services.prompt_templates import list_templates

    return list_templates(category=category, keyword=keyword)


@router.post("/polish", response_model=PolishResponse, summary="电影感提示词润色")
async def polish_prompt(body: PolishRequest):
    if body.stage not in ALLOWED_STAGES:
        raise HTTPException(status_code=400, detail=f"invalid stage: {body.stage}")
    try:
        return run_polish(
            stage=body.stage,
            text_cn=body.input.text_cn,
            text_en=body.input.text_en,
            context=body.input.context,
            return_interpretation=body.options.return_interpretation,
        )
    except (PolishError, LLMError, ValueError) as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{template_id}", response_model=PromptTemplate, summary="获取模板详情")
async def get_template_api(template_id: str):
    from app.services.prompt_templates import get_template

    tpl = get_template(template_id)
    if tpl:
        return tpl
    raise HTTPException(status_code=404, detail="模板不存在")


@router.post("", response_model=PromptTemplate, summary="创建模板")
async def create_template(template: dict):
    from app.db.repositories.prompt_templates import PromptTemplateRepository

    repo = PromptTemplateRepository()
    tpl = repo.create(template)
    return tpl


@router.put("/{template_id}", response_model=PromptTemplate, summary="更新模板")
async def update_template(template_id: str, template: dict):
    from app.db.repositories.prompt_templates import PromptTemplateRepository
    from app.services import prompt_templates as pt

    repo = PromptTemplateRepository()
    existing = repo.get(template_id)
    if existing:
        tpl = repo.update(template_id, template)
    else:
        # 改写种子模板：先持久化一份覆盖，再更新
        base = pt.get_template(template_id)
        payload = {**(base or {}), **template, "id": template_id}
        tpl = repo.create(payload)
        tpl = repo.update(template_id, template)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    return tpl


@router.delete("/{template_id}", summary="删除模板")
async def delete_template(template_id: str):
    from app.db.repositories.prompt_templates import PromptTemplateRepository

    repo = PromptTemplateRepository()
    if not repo.get(template_id):
        # 无持久化覆盖：删除对纯种子无效，视为无操作
        return {"message": "模板为内置默认，无可删除的自定义内容"}
    repo.delete(template_id)
    return {"message": "删除成功"}
