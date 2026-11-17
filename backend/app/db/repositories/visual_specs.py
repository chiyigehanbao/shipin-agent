from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.db.connection import connect
from app.db.schema import migrate


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["spec_json"] = json.loads(item.get("spec_json") or "{}")
    return item


class VisualSpecRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self):
        return connect(self.db_path)

    def get(self, project_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM project_visual_specs WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            return _row(row) if row else None

    def upsert(self, project_id: str, spec: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        payload = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
        version = int(spec.get("version") or 1)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO project_visual_specs
                  (project_id, spec_json, version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                  spec_json = excluded.spec_json,
                  version = excluded.version,
                  updated_at = excluded.updated_at
                """,
                (project_id, payload, version, now, now),
            )
            conn.commit()
        item = self.get(project_id)
        assert item is not None
        return item
