from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.services.storyboard_render.types import (
    StoryboardRenderError,
    StoryboardRenderRequest,
)


class StoryboardRenderWorker:
    def __init__(
        self,
        *,
        requests: Any,
        attempts: Any,
        assets: Any,
        frames: Any,
        jobs: Any,
        client: Any,
        adapters: dict[str, Any],
        output_root: Path,
        media_root: Path,
        identity_evaluator: Any | None = None,
        poll_timeout_sec: float = 600.0,
        poll_interval_sec: float = 1.5,
    ) -> None:
        self.requests = requests
        self.attempts = attempts
        self.assets = assets
        self.frames = frames
        self.jobs = jobs
        self.client = client
        self.adapters = adapters
        self.output_root = Path(output_root)
        self.media_root = Path(media_root)
        self.identity_evaluator = identity_evaluator
        self.poll_timeout_sec = poll_timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="storyboard-render-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put("")
        if self._thread:
            self._thread.join(timeout=5)

    def enqueue(self, attempt_id: str) -> None:
        self._queue.put(attempt_id)

    def pending_count(self) -> int:
        return self._queue.qsize()

    def _run(self) -> None:
        while not self._stop.is_set():
            attempt_id = self._queue.get()
            if attempt_id:
                self.process(attempt_id)

    def resolve_media_path(self, public_url: str) -> Path:
        path = unquote(urlparse(public_url).path)
        if not path.startswith("/media/"):
            raise StoryboardRenderError(
                "reference_upload_invalid", f"无效参考图地址：{public_url}"
            )
        root = self.media_root.resolve()
        resolved = (root / path.removeprefix("/media/")).resolve()
        if root != resolved and root not in resolved.parents:
            raise StoryboardRenderError(
                "reference_upload_invalid", "参考图地址越出 media 目录"
            )
        if not resolved.is_file():
            raise StoryboardRenderError(
                "reference_upload_invalid", f"参考图文件不存在：{public_url}"
            )
        return resolved

    def process(self, attempt_id: str) -> None:
        attempt = self.attempts.get(attempt_id)
        if not attempt or attempt.get("status") != "queued":
            return
        try:
            self.attempts.transition(attempt_id, "running")
            request_row = self.requests.get(attempt["request_id"])
            if request_row is None:
                raise StoryboardRenderError(
                    "render_execution_failed", "渲染请求快照不存在"
                )
            request = StoryboardRenderRequest.model_validate(request_row["request"])
            adapter = self.adapters.get(attempt["adapter"])
            if adapter is None:
                raise StoryboardRenderError(
                    "render_execution_failed", f"未知 Adapter：{attempt['adapter']}"
                )
            identities = sorted(
                request.character_identities, key=lambda item: item.reference_order
            )
            uploaded: list[str] = []
            if attempt["adapter"] == "flux_kontext":
                paths = [
                    self.resolve_media_path(item.reference_image_url)
                    for item in identities
                ]
                uploaded = [self.client.upload_image(path) for path in paths]
            workflow = adapter.build(
                request=request,
                uploaded_images=uploaded,
                seed=attempt["seed"],
            )
            prompt_id = self.client.submit_workflow(workflow)
            meta = self.client.poll_history(
                prompt_id,
                timeout_sec=self.poll_timeout_sec,
                interval_sec=self.poll_interval_sec,
            )
            output_path = self.output_root / attempt["project_id"] / f"{attempt_id}.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.client.download_image(meta, output_path)
            public_url = (
                f"/media/assets/{attempt['project_id']}/{attempt_id}.png"
            )
            self.attempts.transition(
                attempt_id, "candidate", image_url=public_url
            )
            self.assets.update(
                attempt["project_id"],
                attempt["asset_id"],
                status="completed",
                image_url=public_url,
                error=None,
            )
            self.frames.update(
                attempt["project_id"],
                attempt["frame_id"],
                status="candidate",
                error=None,
            )
            try:
                if self.identity_evaluator is None:
                    evaluation = {
                        "status": "unscored",
                        "model_fingerprint": "",
                        "characters": [],
                        "warnings": ["face_model_unavailable"],
                    }
                else:
                    evaluation = self.identity_evaluator.evaluate(
                        identities, output_path
                    )
            except Exception:
                evaluation = {
                    "status": "unscored",
                    "model_fingerprint": "",
                    "characters": [],
                    "warnings": ["identity_evaluation_failed"],
                }
            try:
                self.attempts.set_identity_evaluation(attempt_id, evaluation)
            except Exception:
                pass
            if attempt.get("job_id"):
                self.jobs.update(
                    attempt["job_id"],
                    status="completed",
                    progress=100,
                    result={"attempt_id": attempt_id},
                    finished_at=self._now(),
                )
        except Exception as exc:
            error = {
                "code": getattr(exc, "code", "render_execution_failed"),
                "message": str(exc)[:500],
            }
            message = error["message"]
            try:
                self.attempts.transition(attempt_id, "failed", error=error)
            except Exception:
                pass
            self._safe_update(
                self.assets,
                attempt["project_id"],
                attempt.get("asset_id"),
                status="failed",
                error=message,
            )
            self._safe_update(
                self.frames,
                attempt["project_id"],
                attempt.get("frame_id"),
                status="failed",
                error=message,
            )
            if attempt.get("job_id"):
                try:
                    self.jobs.update(
                        attempt["job_id"],
                        status="failed",
                        error=message,
                        finished_at=self._now(),
                    )
                except Exception:
                    pass

    @staticmethod
    def _safe_update(
        repository: Any, project_id: str, entity_id: str | None, **fields: Any
    ) -> None:
        if not entity_id:
            return
        try:
            repository.update(project_id, entity_id, **fields)
        except Exception:
            pass

    @staticmethod
    def _now() -> str:
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
