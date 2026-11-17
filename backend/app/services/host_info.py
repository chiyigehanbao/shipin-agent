from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore


def _disk_root() -> str:
    if os.name == "nt":
        return Path.cwd().anchor or "C:\\"
    return "/"


def read_host_stats() -> dict[str, Any]:
    if psutil is None:
        return {"cpu_percent": None, "memory_percent": None, "disk_percent": None}
    try:
        return {
            "cpu_percent": float(psutil.cpu_percent(interval=0.0)),
            "memory_percent": float(psutil.virtual_memory().percent),
            "disk_percent": float(psutil.disk_usage(_disk_root()).percent),
        }
    except Exception:
        return {"cpu_percent": None, "memory_percent": None, "disk_percent": None}
