"""Run MiniMax video generation via ComfyUI and persist mp4 under media."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.core.settings import settings
from app.services.comfyui_client import ComfyUIClient, ComfyUIError
from app.services.workflows.minimax import (
    DEFAULT_HEIGHT,
    DEFAULT_LENGTH,
    DEFAULT_WIDTH,
    build_minimax_workflow,
)


class VideoGenerateError(RuntimeError):
    pass


def run_video_generate(
    *,
    project_id: str,
    job_id: str,
    prompt_en: str,
    client: ComfyUIClient,
    mode: str = "t2v",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    length: int = DEFAULT_LENGTH,
    seed: Optional[int] = None,
    first_frame_path: Optional[str] = None,
    timeout_sec: float = 3600.0,
    progress_cb=None,
) -> dict[str, Any]:
    prompt = (prompt_en or "").strip()
    if not prompt:
        raise VideoGenerateError("prompt_en is required")

    first_name: Optional[str] = None
    if (mode or "t2v").lower() == "i2v":
        if not first_frame_path:
            raise VideoGenerateError("first_frame_path is required for i2v")
        path = Path(first_frame_path)
        if not path.is_file():
            raise VideoGenerateError(f"first frame not found: {path}")
        if progress_cb:
            progress_cb(25)
        try:
            first_name = client.upload_image(path)
        except ComfyUIError as e:
            raise VideoGenerateError(str(e)) from e

    try:
        wf = build_minimax_workflow(
            prompt,
            mode=mode,
            width=width,
            height=height,
            length=length,
            seed=seed,
            first_frame_name=first_name,
            filename_prefix=f"vf_minimax/{project_id}/{job_id}",
        )
    except ValueError as e:
        raise VideoGenerateError(str(e)) from e

    if progress_cb:
        progress_cb(35)
    try:
        prompt_id = client.submit_workflow(wf)
    except Exception as e:
        raise VideoGenerateError(f"submit failed: {e}") from e

    if progress_cb:
        progress_cb(45)
    try:
        meta = client.poll_history(
            prompt_id,
            timeout_sec=timeout_sec,
            interval_sec=2.0,
            media_kinds=("videos", "gifs", "images"),
        )
    except ComfyUIError as e:
        raise VideoGenerateError(str(e)) from e

    if progress_cb:
        progress_cb(85)
    out_dir = settings.media_mount_dir / "videos" / project_id
    dest = out_dir / f"{job_id}.mp4"
    try:
        client.download_output(meta, dest)
    except Exception as e:
        raise VideoGenerateError(f"download failed: {e}") from e

    if not dest.is_file() or dest.stat().st_size < 1000:
        raise VideoGenerateError("downloaded video is empty or missing")

    url = f"/media/videos/{project_id}/{job_id}.mp4"
    return {
        "output_url": url,
        "path": str(dest),
        "prompt_id": prompt_id,
        "mode": mode,
        "model": "minimax",
        "width": width,
        "height": height,
        "length": length,
    }
