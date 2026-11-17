# ============================================
# RAG 知识库 API（真实）
# ============================================

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.repositories.scenes import SceneRepository
from app.services.rag_retrieve import get_rag_repo, get_rag_store
from app.services.runtime import store as asset_store
from app.services.runtime import storyboard_store

router = APIRouter()

TYPE_NAME = {
    "character": "角色",
    "scene": "场景",
    "prop": "道具",
    "storyboard": "分镜",
    "technique": "技巧",
}


class RAGCaseOut(BaseModel):
    id: str
    title: str
    type: str
    type_name: str
    style: str = ""
    rating: float = 0
    usage_count: int = 0
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    created_at: str
    prompt_en: str = ""
    negative_prompt: str = ""


class RAGSearchResult(BaseModel):
    case: RAGCaseOut
    similarity: float


class CreateCaseBody(BaseModel):
    title: str
    type: str = "scene"
    style: str = ""
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    prompt_en: str = ""
    negative_prompt: str = ""


class SearchBody(BaseModel):
    query: str
    top_k: int = 5
    type: Optional[str] = None


class IngestBody(BaseModel):
    source_type: str  # scene | asset | frame
    project_id: str
    ref_id: str
    title: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


def _to_out(c: dict[str, Any]) -> dict[str, Any]:
    t = c.get("type") or "scene"
    return {
        "id": c["id"],
        "title": c.get("title") or "",
        "type": t,
        "type_name": TYPE_NAME.get(t, t),
        "style": c.get("style") or "",
        "rating": float(c.get("rating") or 0),
        "usage_count": int(c.get("usage_count") or 0),
        "description": c.get("description") or "",
        "tags": c.get("tags") or [],
        "created_at": c.get("created_at") or "",
        "prompt_en": c.get("prompt_en") or "",
        "negative_prompt": c.get("negative_prompt") or "",
    }


def _require_embedder():
    store = get_rag_store()
    if not store.embedder.available():
        raise HTTPException(status_code=503, detail="bge-m3_not_found")
    return store


def _embed_doc(case: dict[str, Any]) -> str:
    parts = [
        case.get("title") or "",
        case.get("description") or "",
        case.get("prompt_en") or "",
        " ".join(case.get("tags") or []),
    ]
    return "\n".join(p for p in parts if p)


@router.get("/stats", summary="获取知识库统计")
async def get_stats():
    repo = get_rag_repo()
    total = repo.count()
    image_types = ("character", "scene", "prop", "storyboard")
    image_type = sum(repo.count(type=t) for t in image_types)
    return {
        "total": total,
        "image_type": image_type,
        "text_type": max(0, total - image_type),
        "weekly_new": 0,
    }


@router.get("/cases", response_model=List[RAGCaseOut], summary="获取案例列表")
async def get_cases(
    type: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    repo = get_rag_repo()
    offset = max(0, (page - 1) * page_size)
    rows = repo.list(type=type, keyword=keyword, limit=page_size, offset=offset)
    return [_to_out(r) for r in rows]


@router.post("/search", response_model=List[RAGSearchResult], summary="检索案例")
async def search_cases(body: SearchBody):
    store = _require_embedder()
    repo = get_rag_repo()
    try:
        hits = store.query(body.query, top_k=body.top_k, type_filter=body.type)
    except RuntimeError as e:
        if "bge-m3" in str(e):
            raise HTTPException(status_code=503, detail="bge-m3_not_found") from e
        raise
    out = []
    for h in hits:
        case = repo.get(h["id"])
        if not case:
            continue
        out.append({"case": _to_out(case), "similarity": h["similarity"]})
    return out


@router.post("/cases", summary="添加案例")
async def add_case(body: CreateCaseBody):
    store = _require_embedder()
    repo = get_rag_repo()
    case = repo.create(
        title=body.title,
        type=body.type,
        style=body.style,
        description=body.description,
        tags=body.tags,
        prompt_en=body.prompt_en,
        negative_prompt=body.negative_prompt,
    )
    try:
        store.upsert(
            case_id=case["id"],
            document=_embed_doc(case),
            metadata={"type": case["type"], "title": case["title"]},
        )
    except RuntimeError as e:
        repo.delete(case["id"])
        if "bge-m3" in str(e):
            raise HTTPException(status_code=503, detail="bge-m3_not_found") from e
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"id": case["id"], "message": "案例添加成功", "case": _to_out(case)}


@router.delete("/cases/{case_id}", summary="删除案例")
async def delete_case(case_id: str):
    repo = get_rag_repo()
    store = get_rag_store()
    ok = repo.delete(case_id)
    store.delete(case_id)
    if not ok:
        raise HTTPException(status_code=404, detail="案例不存在")
    return {"message": "删除成功"}


@router.post("/ingest", summary="从工作台入库")
async def ingest(body: IngestBody):
    store = _require_embedder()
    repo = get_rag_repo()
    title = body.title or ""
    description = ""
    prompt_en = ""
    negative = ""
    ctype = "scene"
    style = ""

    if body.source_type == "scene":
        scene = SceneRepository().get(body.project_id, body.ref_id)
        if not scene:
            raise HTTPException(status_code=404, detail="场景不存在")
        title = title or scene.get("name") or body.ref_id
        description = scene.get("description") or scene.get("interpretation_cn") or ""
        prompt_en = scene.get("prompt_en") or ""
        negative = scene.get("negative_prompt") or ""
        ctype = "scene"
    elif body.source_type == "asset":
        asset = asset_store.get(body.project_id, body.ref_id)
        if not asset:
            raise HTTPException(status_code=404, detail="资产不存在")
        title = title or asset.get("name") or body.ref_id
        description = asset.get("prompt_cn") or ""
        prompt_en = asset.get("prompt_en") or ""
        negative = asset.get("negative_prompt") or ""
        ctype = asset.get("type") or "character"
    elif body.source_type == "frame":
        frame = storyboard_store.get(body.project_id, body.ref_id)
        if not frame:
            raise HTTPException(status_code=404, detail="分镜不存在")
        title = title or f"分镜 {frame.get('number') or body.ref_id}"
        description = frame.get("description") or ""
        prompt_en = frame.get("prompt_en") or ""
        negative = frame.get("negative_prompt") or ""
        ctype = "storyboard"
    else:
        raise HTTPException(status_code=400, detail=f"unknown source_type: {body.source_type}")

    case = repo.create(
        title=title,
        type=ctype if ctype in TYPE_NAME else "scene",
        style=style,
        description=description,
        tags=body.tags,
        prompt_en=prompt_en,
        negative_prompt=negative,
        source_project_id=body.project_id,
        source_ref=f"{body.source_type}:{body.ref_id}",
    )
    try:
        store.upsert(
            case_id=case["id"],
            document=_embed_doc(case),
            metadata={"type": case["type"], "title": case["title"]},
        )
    except Exception as e:
        repo.delete(case["id"])
        if "bge-m3" in str(e):
            raise HTTPException(status_code=503, detail="bge-m3_not_found") from e
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"id": case["id"], "message": "入库成功", "case": _to_out(case)}
