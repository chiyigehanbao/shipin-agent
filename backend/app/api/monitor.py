from fastapi import APIRouter, HTTPException
from datetime import datetime

from app.services.monitor_snapshot import build_snapshot
from app.services.runtime import job_queue, job_repo

router = APIRouter()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@router.get("/snapshot", summary="监控快照")
async def get_snapshot():
    return build_snapshot()


@router.get("/system", summary="获取系统状态")
async def get_system_stats():
    s = build_snapshot()
    gpu = s["gpu"]
    return {
        "cpu": s["host"].get("cpu_percent") or 0,
        "memory": s["host"].get("memory_percent") or 0,
        "gpu": gpu.get("utilization_percent") or 0,
        "disk": s["host"].get("disk_percent") or 0,
    }


@router.get("/acestep", summary="ACE-Step 音乐服务状态")
async def get_acestep():
    from app.services import ace_step

    return {"online": ace_step.is_available(timeout=1.0), "base_url": ace_step.ACE_STEP_BASE}


@router.get("/tasks", summary="获取任务队列")
async def get_task_queue():
    s = build_snapshot()
    return s["tasks"]["generating"] + s["tasks"]["failed_recent"]


def _get_task_or_404(task_id: str) -> dict:
    job = job_repo.get(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.post("/tasks/{task_id}/pause", summary="暂停任务")
async def pause_task(task_id: str):
    """暂停排队中的任务（进行中任务无法中断，返回提示）。"""
    job = _get_task_or_404(task_id)
    if job["status"] not in ("queued", "running"):
        raise HTTPException(
            status_code=400, detail=f"任务当前状态为 {job['status']}，无法暂停"
        )
    if job["status"] == "running":
        return {
            "task_id": task_id,
            "status": "running",
            "message": "任务正在执行无法立即暂停，可先取消后重新编排",
        }
    job_repo.update(task_id, status="paused", finished_at=_now())
    return {"task_id": task_id, "status": "paused", "message": "已暂停"}


@router.post("/tasks/{task_id}/resume", summary="恢复任务")
async def resume_task(task_id: str):
    """恢复已暂停的任务并入队。"""
    job = _get_task_or_404(task_id)
    if job["status"] != "paused":
        raise HTTPException(
            status_code=400, detail=f"任务当前状态为 {job['status']}，无需恢复"
        )
    job_repo.update(task_id, status="queued", error=None, started_at=None)
    job_queue.enqueue(task_id)
    return {"task_id": task_id, "status": "queued", "message": "已恢复并入队"}


@router.post("/tasks/{task_id}/cancel", summary="取消任务")
async def cancel_task(task_id: str):
    """取消排队/运行中的任务。"""
    job = _get_task_or_404(task_id)
    if job["status"] in ("completed", "cancelled"):
        return {
            "task_id": task_id,
            "status": job["status"],
            "message": "任务已终止，无需重复取消",
        }
    job_queue.request_cancel(task_id)
    job_repo.update(
        task_id, status="cancelled", error="cancelled", finished_at=_now()
    )
    return {"task_id": task_id, "status": "cancelled", "message": "已请求取消"}

