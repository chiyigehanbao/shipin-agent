from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.db.connection import connect
from app.db.schema import migrate


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class RenderRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self):
        return connect(self.db_path)

    def create(self, **fields: Any) -> dict[str, Any]:
        item = {
            "id": fields.get("id") or f"render_{uuid.uuid4().hex[:8]}",
            "project_id": fields["project_id"],
            "scene_id": fields.get("scene_id"),
            "status": fields.get("status") or "completed",
            "engine": fields.get("engine") or "edge",
            "output_url": fields.get("output_url"),
            "duration_sec": fields.get("duration_sec"),
            "error": fields.get("error"),
            "created_at": _now(),
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO renders (
                  id, project_id, scene_id, status, engine, output_url,
                  duration_sec, error, created_at
                ) VALUES (
                  :id, :project_id, :scene_id, :status, :engine, :output_url,
                  :duration_sec, :error, :created_at
                )
                """,
                item,
            )
            conn.commit()
        return item

    def list_by_project(self, project_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM renders WHERE project_id = ?
                ORDER BY created_at DESC
                """,
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]
