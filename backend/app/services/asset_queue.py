# ============================================
# 资产生成串行队列 + worker
# ============================================
# 单 worker 串行出图，遵守 16GB 显存约束
# （LTX/MiniMax 不同时加载，一次只跑一张）。
# ============================================

from __future__ import annotations

import httpx
import queue
import threading
from pathlib import Path
from typing import Any, Callable

from app.services.asset_store import AssetStore
from app.services.comfyui_client import ComfyUIError
from app.services.workflows import resolve_aspect_size


class AssetQueue:
    def __init__(
        self,
        *,
        store: AssetStore,
        client: Any,
        output_root: Path,
        build_workflow: Callable[..., dict[str, Any]],
        poll_timeout_sec: float = 600.0,
        poll_interval_sec: float = 1.5,
    ) -> None:
        self.store = store
        self.client = client
        self.output_root = output_root
        self.build_workflow = build_workflow
        self.poll_timeout_sec = poll_timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self._q: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="asset-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._q.put(("", ""))
        if self._thread:
            self._thread.join(timeout=5)

    def enqueue(self, project_id: str, asset_id: str) -> None:
        self._q.put((project_id, asset_id))

    def pending_count(self) -> int:
        return self._q.qsize()

    def _run(self) -> None:
        while not self._stop.is_set():
            project_id, asset_id = self._q.get()
            if not asset_id:
                continue
            self._process(project_id, asset_id)

    def _process(self, project_id: str, asset_id: str) -> None:
        asset = self.store.get(project_id, asset_id)
        if not asset:
            return
        if not self.client.health():
            self.store.update(
                project_id, asset_id, status="failed", error="comfyui_unavailable"
            )
            self._finish_linked_job(asset_id, ok=False, error="comfyui_unavailable")
            return
        prompt = asset["prompt_en"] or asset["prompt_cn"]
        negative = asset.get("negative_prompt") or ""
        try:
            from app.services.prompt_templates import (
                get_template,
                sampler_overrides_for_model,
                template_for_asset_type,
            )

            tpl = None
            tid = (asset.get("template_id") or "").strip()
            if tid:
                tpl = get_template(tid)
            if tpl is None:
                tpl = template_for_asset_type(str(asset.get("type") or ""))
            if not (negative or "").strip() and tpl:
                negative = str(tpl.get("negative_prompt_en") or "")
            overrides = sampler_overrides_for_model(tpl, str(asset.get("model") or "flux"))
            width, height = resolve_aspect_size(str(asset.get("aspect") or ""))
            workflow = self.build_workflow(
                asset["model"],
                prompt,
                negative,
                width=width,
                height=height,
                **overrides,
            )
            prompt_id = self.client.submit_workflow(workflow)
            meta = self.client.poll_history(
                prompt_id,
                timeout_sec=self.poll_timeout_sec,
                interval_sec=self.poll_interval_sec,
            )
            dest = self.output_root / project_id / f"{asset_id}.png"
            self.client.download_image(meta, dest)
            url = f"/media/assets/{project_id}/{asset_id}.png"
            self.store.update(
                project_id, asset_id, status="completed", image_url=url, error=None
            )
        except (ComfyUIError, OSError, httpx.HTTPError, Exception) as e:
            self.store.update(
                project_id, asset_id, status="failed", error=str(e)[:300]
            )
            self._finish_linked_job(asset_id, ok=False, error=str(e)[:300])
            return
        self._finish_linked_job(asset_id, ok=True, error=None)

    def _finish_linked_job(
        self, asset_id: str, *, ok: bool, error: str | None
    ) -> None:
        try:
            from app.services.runtime import job_repo
        except Exception:
            return
        job = job_repo.find_active_by_asset(asset_id)
        if not job:
            return
        from datetime import datetime

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if ok:
            job_repo.update(
                job["id"],
                status="completed",
                progress=100,
                result={"asset_id": asset_id},
                finished_at=now,
            )
        else:
            job_repo.update(
                job["id"],
                status="failed",
                error=error or "failed",
                finished_at=now,
            )
