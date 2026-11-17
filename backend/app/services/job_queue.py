from __future__ import annotations

import queue
import threading
from datetime import datetime
from typing import Any, Callable

from app.db.repositories.jobs import JobRepository


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class JobQueue:
    def __init__(
        self,
        *,
        repo: JobRepository,
        dispatch: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> None:
        self.repo = repo
        self.dispatch = dispatch
        self._q: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._cancel: set[str] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="job-worker", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._q.put("")
        if self._thread:
            self._thread.join(timeout=5)

    def enqueue(self, job_id: str) -> None:
        self._q.put(job_id)

    def request_cancel(self, job_id: str) -> None:
        self._cancel.add(job_id)

    def bootstrap_fail_stale(self) -> int:
        return self.repo.fail_stale(error="server_restarted")

    def _run(self) -> None:
        while not self._stop.is_set():
            job_id = self._q.get()
            if not job_id:
                continue
            self._process(job_id)

    def _process(self, job_id: str) -> None:
        job = self.repo.get(job_id)
        if not job or job["status"] not in ("queued", "running"):
            return
        if job_id in self._cancel:
            self._cancel.discard(job_id)
            self.repo.update(
                job_id, status="cancelled", finished_at=_now(), error="cancelled"
            )
            return
        self.repo.update(job_id, status="running", progress=5, started_at=_now())
        try:
            result = self.dispatch(self.repo.get(job_id) or job) or {}
            if job_id in self._cancel:
                self._cancel.discard(job_id)
                self.repo.update(
                    job_id, status="cancelled", finished_at=_now(), error="cancelled"
                )
                return
            self.repo.update(
                job_id,
                status="completed",
                progress=100,
                result=result,
                finished_at=_now(),
            )
        except Exception as e:
            self.repo.update(
                job_id,
                status="failed",
                error=str(e)[:500],
                finished_at=_now(),
            )
