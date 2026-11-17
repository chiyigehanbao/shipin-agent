# ============================================
# 项目管理 API（SQLite）
# ============================================

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.repositories.projects import ProjectRepository

router = APIRouter()
_repo = ProjectRepository()


class ProjectBase(BaseModel):
    name: str
    type: str
    description: Optional[str] = None
    style: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class Project(ProjectBase):
    id: str
    status: str
    progress: int
    episode_count: int
    created_at: str
    updated_at: str
    current_step: int

    class Config:
        from_attributes = True


@router.get("", response_model=List[Project], summary="获取项目列表")
async def get_projects(
    type: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
):
    return _repo.list_all(type=type, status=status, keyword=keyword)


@router.get("/{project_id}", response_model=Project, summary="获取项目详情")
async def get_project(project_id: str):
    item = _repo.get(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return item


@router.post("", response_model=Project, summary="创建新项目")
async def create_project(project: ProjectCreate):
    return _repo.create(
        name=project.name,
        type=project.type,
        description=project.description or "",
        style=project.style or "",
    )


@router.put("/{project_id}", response_model=Project, summary="更新项目")
async def update_project(project_id: str, project: ProjectCreate):
    try:
        return _repo.update(
            project_id,
            name=project.name,
            type=project.type,
            description=project.description or "",
            style=project.style or "",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="项目不存在") from None


@router.delete("/{project_id}", summary="删除项目")
async def delete_project(project_id: str):
    try:
        _repo.delete(project_id)
        return {"message": "删除成功"}
    except KeyError:
        raise HTTPException(status_code=404, detail="项目不存在") from None


@router.post("/{project_id}/archive", response_model=Project, summary="归档项目")
async def archive_project(project_id: str):
    try:
        return _repo.update(project_id, status="archived")
    except KeyError:
        raise HTTPException(status_code=404, detail="项目不存在") from None


@router.post("/{project_id}/complete", summary="完成项目并沉淀经验")
async def complete_project(project_id: str):
    """标记项目完成，并把剧本/资产/分镜提示词自动入库 RAG（best-effort）。"""
    try:
        item = _repo.get(project_id)
    except Exception:
        item = None
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    from app.services.rag_auto_ingest import auto_ingest_project

    try:
        _repo.update(project_id, status="completed")
    except Exception:
        pass
    counts = auto_ingest_project(project_id)
    return {"status": "completed", "ingested": counts, "message": "项目已完成并沉淀经验"}
