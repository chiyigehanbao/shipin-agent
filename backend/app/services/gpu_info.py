from __future__ import annotations

import subprocess
from typing import Any


def _unavailable(error: str) -> dict[str, Any]:
    return {
        "available": False,
        "name": None,
        "temperature_c": None,
        "utilization_percent": None,
        "memory_used_mb": None,
        "memory_total_mb": None,
        "error": error,
    }


def parse_nvidia_smi_csv(text: str) -> dict[str, Any]:
    lines = (text or "").strip().splitlines()
    if not lines:
        return _unavailable("nvidia-smi empty")
    parts = [p.strip() for p in lines[0].split(",")]
    if len(parts) < 5:
        return _unavailable("nvidia-smi parse error")
    try:
        return {
            "available": True,
            "name": parts[0],
            "temperature_c": int(float(parts[1])),
            "utilization_percent": int(float(parts[2])),
            "memory_used_mb": int(float(parts[3])),
            "memory_total_mb": int(float(parts[4])),
            "error": None,
        }
    except ValueError:
        return _unavailable("nvidia-smi parse error")


def _run_nvidia_smi() -> str:
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1.0, check=False)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "nvidia-smi failed").strip()[:200])
    return r.stdout


def read_gpu_stats() -> dict[str, Any]:
    try:
        return parse_nvidia_smi_csv(_run_nvidia_smi())
    except Exception as e:
        return _unavailable(str(e)[:200])
