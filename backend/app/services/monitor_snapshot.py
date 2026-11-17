from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx

from app.core.settings import settings
from app.services.gpu_info import read_gpu_stats
from app.services.host_info import read_host_stats
from app.services.llm_runtime import effective_llm_kwargs
from app.services.runtime import job_repo, queue, store

# GPU / host / remote probes are expensive; reuse for a few seconds.
_PROBE_TTL_SEC = 3.0
_probe_cache: dict[str, Any] | None = None
_probe_cache_at: float = 0.0


def _job_task_row(j: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": j["id"],
        "project_id": j.get("project_id") or "",
        "name": j.get("title") or j["id"],
        "type": j.get("type") or "",
        "status": j["status"],
        "model": "",
        "error": j.get("error"),
        "created_at": j.get("created_at") or "",
        "link_path": j.get("link_path"),
        "progress": j.get("progress") or 0,
    }


def _probe_comfy_online() -> bool:
    try:
        from app.services.runtime import client

        return bool(client.health())
    except Exception:
        return False


def _probe_ollama(kw: dict[str, Any]) -> tuple[bool, str]:
    model = kw.get("ollama_model") or ""
    base = (kw.get("ollama_base_url") or "").rstrip("/")
    if not base:
        return False, model
    try:
        r = httpx.get(f"{base}/api/tags", timeout=0.4, trust_env=False)
        return r.status_code == 200, model
    except Exception:
        return False, model


def _probe_ace_step() -> bool:
    try:
        from app.services.ace_step import is_available

        return is_available(timeout=0.4)
    except Exception:
        return False


def clear_probe_cache() -> None:
    global _probe_cache, _probe_cache_at
    _probe_cache = None
    _probe_cache_at = 0.0


def _read_probes(*, comfy_online: bool | None = None) -> dict[str, Any]:
    global _probe_cache, _probe_cache_at
    now = time.monotonic()
    use_cache = comfy_online is None and _probe_cache is not None and (now - _probe_cache_at) < _PROBE_TTL_SEC
    if use_cache:
        cached = _probe_cache
        assert cached is not None
        # Live queue depth even when reusing probe cache
        services = dict(cached["services"])
        comfy = dict(services.get("comfyui") or {})
        comfy["queue"] = store.queue_depth() + queue.pending_count()
        services["comfyui"] = comfy
        return {
            "host": cached["host"],
            "gpu": cached["gpu"],
            "services": services,
        }

    if comfy_online is None:
        comfy_online = _probe_comfy_online()

    kw = effective_llm_kwargs()
    ollama_online, ollama_model = _probe_ollama(kw)

    probes = {
        "host": read_host_stats(),
        "gpu": read_gpu_stats(),
        "services": {
            "comfyui": {
                "online": bool(comfy_online),
                "queue": store.queue_depth() + queue.pending_count(),
            },
            "ollama": {
                "online": ollama_online,
                "model": ollama_model,
            },
            "acestep": {
                "online": _probe_ace_step(),
            },
        },
    }
    _probe_cache = probes
    _probe_cache_at = now
    return probes


def build_snapshot(*, comfy_online: bool | None = None) -> dict[str, Any]:
    generating = [_job_task_row(j) for j in job_repo.list_active(limit=50)]
    failed = [_job_task_row(j) for j in job_repo.list_recent_failed(limit=20)]
    probes = _read_probes(comfy_online=comfy_online)

    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "host": probes["host"],
        "gpu": probes["gpu"],
        "services": probes["services"],
        "tasks": {
            "badge_count": len(generating),
            "generating": generating,
            "failed_recent": failed,
        },
    }
