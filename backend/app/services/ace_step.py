# ============================================
# ACE-Step 1.5 音乐生成客户端（本地 REST API）
# 用于成片 BGM：POST /release_task → POST /query_result → GET /v1/audio
# ============================================
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import httpx

ACE_STEP_BASE = os.environ.get("ACE_STEP_BASE_URL", "http://127.0.0.1:8001")
DEFAULT_POLL_TIMEOUT_SEC = 600.0
DEFAULT_POLL_INTERVAL_SEC = 5.0

DEFAULT_ROYALTY_FREE_BGM_HINT = (
    "cinematic ambient background music, instrumental only, no vocals, "
    "emotional underscore, soft pads, subtle, layering drama"
)


class AceStepError(RuntimeError):
    pass


def is_available(timeout: float = 3.0) -> bool:
    """ACE-Step API 是否在线。"""
    try:
        r = httpx.get(f"{ACE_STEP_BASE}/health", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def generate_bgm(
    *,
    caption: str,
    duration_sec: float,
    out_path: Path | str,
    bpm: int | None = None,
    key_scale: str | None = None,
    time_signature: str = "4/4",
    poll_timeout_sec: float = DEFAULT_POLL_TIMEOUT_SEC,
    poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC,
) -> str:
    """生成一段器乐 BGM 并保存为 MP3，返回输出路径。"""
    payload: dict[str, Any] = {
        "prompt": (caption or "").strip() or DEFAULT_ROYALTY_FREE_BGM_HINT,
        "lyrics": "[inst]",
        "vocal_language": "instrumental",
        "audio_format": "mp3",
        "audio_duration": float(max(10, min(600, duration_sec))),
        "thinking": False,
        "use_cot_caption": True,
        "use_format": False,
        "use_random_seed": True,
        "time_signature": time_signature or "4/4",
    }
    if bpm:
        payload["bpm"] = int(bpm)
    if key_scale:
        payload["key_scale"] = key_scale

    with httpx.Client(timeout=30) as client:
        res = client.post(f"{ACE_STEP_BASE}/release_task", json=payload)
        res.raise_for_status()
        body = res.json()
        task_id = None
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, dict):
                task_id = data.get("task_id")
            if task_id is None:
                task_id = body.get("task_id")
        if not task_id:
            raise AceStepError("release_task 响应缺少 task_id")

        deadline = time.time() + poll_timeout_sec
        while time.time() < deadline:
            time.sleep(poll_interval_sec)
            q = client.post(
                f"{ACE_STEP_BASE}/query_result", json={"task_id_list": [task_id]}
            )
            q.raise_for_status()
            arr = (q.json() or {}).get("data") or []
            if not arr:
                continue
            item = arr[0]
            status = item.get("status")
            if status == 1:
                entries = _parse_result(item.get("result") or "")
                file_path = entries[0].get("file") if entries else None
                if not file_path:
                    raise AceStepError("任务完成但无音频文件路径")
                url = f"{ACE_STEP_BASE}{file_path}"
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    dest = Path(out_path)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with dest.open("wb") as f:
                        for chunk in resp.iter_bytes():
                            f.write(chunk)
                return str(dest.resolve())
            if status == 2:
                raise AceStepError("ACE-Step 任务失败")
        raise AceStepError("ACE-Step 生成超时")


def _parse_result(raw: str | list) -> list[dict]:
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []
