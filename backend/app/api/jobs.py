# ============================================
# 后台任务 API
# ============================================

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.runtime import job_queue, job_repo

router = APIRouter()

TITLE_BY_TYPE = {
    "script_expand": "剧本扩写",
    "script_analyze": "剧本解析",
    "prompt_polish": "电影感润色",
    "prompt_polish_batch": "本集全部润色",
    "asset_generate": "资产生成",
    "storyboard_generate": "分镜出图",
    "storyboard_breakdown": "分镜规划",
    "render_compose": "成片合成",
    "video_generate": "MiniMax 视频生成",
}

LINK_BY_TYPE = {
    "script_expand": "/workbench/{pid}/script",
    "script_analyze": "/workbench/{pid}/script",
    "prompt_polish": "/workbench/{pid}/script",
    "prompt_polish_batch": "/workbench/{pid}/script",
    "asset_generate": "/workbench/{pid}/assets",
    "storyboard_generate": "/workbench/{pid}/storyboard",
    "storyboard_breakdown": "/workbench/{pid}/storyboard",
    "render_compose": "/workbench/{pid}/render",
    "video_generate": "/workbench/{pid}/storyboard",
}

# Types executed by JobQueue worker (LLM). Image types are linked separately.
LLM_JOB_TYPES = {
    "script_expand",
    "script_analyze",
    "prompt_polish",
    "prompt_polish_batch",
    "storyboard_breakdown",
    "render_compose",
    "video_generate",
}


class CreateJobBody(BaseModel):
    type: str
    project_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("")
def create_job(body: CreateJobBody):
    if body.type not in TITLE_BY_TYPE:
        raise HTTPException(status_code=400, detail=f"unknown type: {body.type}")
    link = LINK_BY_TYPE[body.type].format(pid=body.project_id)
    job = job_repo.create(
        type=body.type,
        project_id=body.project_id,
        title=body.payload.get("title") or TITLE_BY_TYPE[body.type],
        payload=body.payload,
        link_path=link,
    )
    if body.type in LLM_JOB_TYPES:
        job_queue.enqueue(job["id"])
    return job


@router.get("")
def list_jobs(
    status: str = "active",
    project_id: Optional[str] = None,
    limit: int = 50,
):
    if status == "active":
        return job_repo.list_active(project_id=project_id, limit=limit)
    active = job_repo.list_active(project_id=project_id, limit=limit)
    failed = job_repo.list_recent_failed(limit=limit)
    if project_id:
        failed = [j for j in failed if j.get("project_id") == project_id]
    return active + failed


@router.get("/{job_id}")
def get_job(job_id: str):
    job = job_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    job = job_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] == "queued":
        return job_repo.update(job_id, status="cancelled", error="cancelled")
    if job["status"] == "running":
        job_queue.request_cancel(job_id)
        return {"ok": True, "message": "cancel requested"}
    return job


@router.post("/{job_id}/retry", summary="重试失败任务")
def retry_job(job_id: str):
    job = job_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] != "failed":
        raise HTTPException(
            status_code=400,
            detail=f"job status is {job['status']}; only failed can be retried",
        )
    if job["type"] in ("asset_generate", "storyboard_generate"):
        raise HTTPException(
            status_code=400,
            detail="此任务由资产生成队列驱动，请在对应资产/分镜页点「重新生成」",
        )
    job_repo.update(job_id, status="queued", error=None, finished_at=None)
    job_queue.enqueue(job_id)
    return job_repo.get(job_id)
