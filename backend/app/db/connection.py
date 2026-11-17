from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.settings import settings


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or settings.resolved_sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
