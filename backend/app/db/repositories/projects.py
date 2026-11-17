from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.db.connection import connect
from app.db.schema import migrate


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ProjectRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self):
        return connect(self.db_path)

    def list_all(
        self,
        *,
        type: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM projects WHERE 1=1"
        params: list[Any] = []
        if type:
            sql += " AND type = ?"
            params.append(type)
        if status:
            sql += " AND status = ?"
            params.append(status)
        if keyword:
            sql += " AND LOWER(name) LIKE ?"
            params.append(f"%{keyword.lower()}%")
        sql += " ORDER BY updated_at DESC"
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    def get(self, project_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            return dict(row) if row else None

    def create(
        self,
        *,
        name: str,
        type: str,
        description: str = "",
        style: str = "",
    ) -> dict[str, Any]:
        now = _now()
        item = {
            "id": f"proj_{uuid.uuid4().hex[:10]}",
            "name": name,
            "type": type,
            "description": description or "",
            "style": style or "",
            "status": "draft",
            "progress": 0,
            "episode_count": 1,
            "current_step": 1,
            "created_at": now,
            "updated_at": now,
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                  id, name, type, description, style, status, progress,
                  episode_count, current_step, created_at, updated_at
                ) VALUES (
                  :id, :name, :type, :description, :style, :status, :progress,
                  :episode_count, :current_step, :created_at, :updated_at
                )
                """,
                item,
            )
            conn.commit()
        return item

    def update(self, project_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "name",
            "type",
            "description",
            "style",
            "status",
            "progress",
            "episode_count",
            "current_step",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            item = self.get(project_id)
            if not item:
                raise KeyError(project_id)
            return item
        updates["updated_at"] = _now()
        sets = ", ".join(f"{k} = :{k}" for k in updates)
        updates["id"] = project_id
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE projects SET {sets} WHERE id = :id", updates
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(project_id)
        item = self.get(project_id)
        assert item is not None
        return item

    def delete(self, project_id: str) -> None:
        """级联删除项目及其所有从属数据（场景/资产/分帧/任务/渲染）。"""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            if cur.rowcount == 0:
                raise KeyError(project_id)
            for table in ("scenes", "assets", "storyboard_frames", "jobs", "renders"):
                conn.execute(
                    f"DELETE FROM {table} WHERE project_id = ?", (project_id,)
                )
            conn.commit()
