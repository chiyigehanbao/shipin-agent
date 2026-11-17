# ============================================
# 成片合成 API
# ============================================
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.repositories.frames import FrameRepository
from app.db.repositories.renders import RenderRepository
from app.db.repositories.scenes import SceneRepository
from app.services.runtime import job_queue, job_repo

router = APIRouter()


class Episode(BaseModel):
    id: str
    number: int
    title: str
    title_en: str = ""
    duration: str = ""
    status: str
    frame_count: int = 0
    video_url: Optional[str] = None


def _dur(render: dict | None) -> str:
    sec = (render or {}).get("duration_sec")
    if not sec:
        return ""
    s = int(float(sec))
    return f"{s // 60:02d}:{s % 60:02d}"


class RenderRequest(BaseModel):
    episode_id: str = "__all__"
    voice_enabled: bool = True
    bgm_enabled: bool = False
    bgm_caption: str = ""
    subtitle_enabled: bool = False
    resolution: str = "1080p"
    fps: int = 24
    engine: str = "edge"


@router.get("/{project_id}/episodes", response_model=List[Episode], summary="获取剧集列表")
async def get_episodes(project_id: str):
    scenes = SceneRepository().list_by_project(project_id)
    frames = FrameRepository().list(project_id)
    renders = RenderRepository().list_by_project(project_id)
    all_render = next((r for r in renders if not r.get("scene_id") and r.get("output_url")), renders[0] if renders else None)
    items: list[dict] = [
        {
            "id": "__all__",
            "number": 0,
            "title": "整片",
            "title_en": "Full",
            "duration": _dur(all_render),
            "status": "completed" if all_render and all_render.get("output_url") else "pending",
            "frame_count": len(frames),
            "video_url": all_render.get("output_url") if all_render else None,
        }
    ]
    for i, s in enumerate(scenes, start=1):
        fc = sum(1 for f in frames if f.get("scene_id") == s["id"])
        sr = next((r for r in renders if r.get("scene_id") == s["id"] and r.get("output_url")), None)
        items.append(
            {
                "id": s["id"],
                "number": i,
                "title": s.get("name") or f"场景{i}",
                "title_en": "",
                "duration": _dur(sr),
                "status": "completed" if sr else "pending",
                "frame_count": fc,
                "video_url": sr.get("output_url") if sr else None,
            }
        )
    return items


@router.get("/{project_id}/episodes/{episode_id}", response_model=Episode, summary="获取剧集详情")
async def get_episode(project_id: str, episode_id: str):
    for ep in await get_episodes(project_id):
        if ep["id"] == episode_id:
            return ep
    raise HTTPException(status_code=404, detail="剧集不存在")


@router.get("/{project_id}/renders", summary="成片历史")
async def list_renders(project_id: str):
    return RenderRepository().list_by_project(project_id)


@router.post("/{project_id}/render", summary="开始合成")
async def start_render(project_id: str, request: RenderRequest):
    if request.bgm_enabled:
        # 本轮未实现 BGM；忽略开关不假装成功混音
        pass
    job = job_repo.create(
        type="render_compose",
        project_id=project_id,
        title="成片合成",
        payload={
            "episode_id": request.episode_id,
            "scene_id": None if request.episode_id == "__all__" else request.episode_id,
            "engine": request.engine or "edge",
            "voice_enabled": request.voice_enabled,
            "subtitle_enabled": request.subtitle_enabled,
            "resolution": request.resolution,
            "fps": request.fps,
            "bgm_enabled": request.bgm_enabled,
            "bgm_caption": request.bgm_caption or "",
        },
        link_path=f"/workbench/{project_id}/render",
    )
    job_queue.enqueue(job["id"])
    return {
        "task_id": job["id"],
        "job_id": job["id"],
        "status": "queued",
        "message": "合成任务已入队",
    }


@router.get("/{project_id}/render/{task_id}/status", summary="查询合成状态")
async def get_render_status(project_id: str, task_id: str):
    job = job_repo.get(task_id)
    if not job or job.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = job.get("result") or {}
    return {
        "task_id": task_id,
        "status": job.get("status"),
        "progress": job.get("progress") or 0,
        "output_url": result.get("output_url"),
        "error": job.get("error"),
        "current_stage": job.get("title") or "",
    }
