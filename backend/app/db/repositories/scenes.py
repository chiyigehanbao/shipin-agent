from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.db.connection import connect
from app.db.schema import migrate
from app.services.script_lines import counts_from_lines, normalize_lines


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_scene(row: dict[str, Any]) -> dict[str, Any]:
    lines = normalize_lines(json.loads(row.get("lines_json") or "[]"))
    d_count, n_count = counts_from_lines(lines)
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "number": row["number"],
        "name": row["name"] or "",
        "location": row["location"] or "",
        "time": row["time"] or "",
        "characters": json.loads(row["characters_json"] or "[]"),
        "props": json.loads(row["props_json"] or "[]"),
        "look_states": json.loads(row.get("look_states_json") or "{}"),
        "description": row.get("description") or "",
        "description_en": row.get("description_en") or "",
        "prompt_cn": row.get("prompt_cn") or "",
        "prompt_en": row.get("prompt_en") or "",
        "negative_prompt": row.get("negative_prompt") or "",
        "interpretation_cn": row.get("interpretation_cn") or "",
        "lines": lines,
        "dialogue_count": d_count,
        "narration_count": n_count,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class SceneRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self):
        return connect(self.db_path)

    def list_by_project(self, project_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM scenes WHERE project_id = ? ORDER BY number ASC",
                (project_id,),
            ).fetchall()
            return [_row_to_scene(dict(r)) for r in rows]

    def get(self, project_id: str, scene_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM scenes WHERE project_id = ? AND id = ?",
                (project_id, scene_id),
            ).fetchone()
            return _row_to_scene(dict(row)) if row else None

    def replace_all(self, project_id: str, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = _now()
        with self._conn() as conn:
            conn.execute("DELETE FROM scenes WHERE project_id = ?", (project_id,))
            out: list[dict[str, Any]] = []
            for i, s in enumerate(scenes, start=1):
                lines = normalize_lines(s.get("lines"))
                d_count, n_count = counts_from_lines(lines)
                item = {
                    "id": s.get("id") or f"scene_{uuid.uuid4().hex[:8]}",
                    "project_id": project_id,
                    "number": int(s.get("number") or i),
                    "name": s.get("name") or "",
                    "location": s.get("location") or "",
                    "time": s.get("time") or "",
                    "characters_json": json.dumps(
                        s.get("characters") or [], ensure_ascii=False
                    ),
                    "props_json": json.dumps(s.get("props") or [], ensure_ascii=False),
                    "look_states_json": json.dumps(
                        s.get("look_states") or {}, ensure_ascii=False, sort_keys=True
                    ),
                    "description": s.get("description") or "",
                    "description_en": s.get("description_en") or "",
                    "prompt_cn": s.get("prompt_cn") or "",
                    "prompt_en": s.get("prompt_en") or "",
                    "negative_prompt": s.get("negative_prompt") or "",
                    "interpretation_cn": s.get("interpretation_cn") or "",
                    "lines_json": json.dumps(lines, ensure_ascii=False),
                    "dialogue_count": d_count,
                    "narration_count": n_count,
                    "created_at": now,
                    "updated_at": now,
                }
                conn.execute(
                    """
                    INSERT INTO scenes (
                      id, project_id, number, name, location, time, characters_json,
                      props_json, look_states_json,
                      description, description_en, prompt_cn, prompt_en, negative_prompt,
                      interpretation_cn, dialogue_count, narration_count, lines_json,
                      created_at, updated_at
                    ) VALUES (
                      :id, :project_id, :number, :name, :location, :time, :characters_json,
                      :props_json, :look_states_json,
                      :description, :description_en, :prompt_cn, :prompt_en, :negative_prompt,
                      :interpretation_cn, :dialogue_count, :narration_count, :lines_json,
                      :created_at, :updated_at
                    )
                    """,
                    item,
                )
                out.append(_row_to_scene(item))
            conn.commit()
        return out

    def update(self, project_id: str, scene_id: str, **fields: Any) -> dict[str, Any]:
        mapping = {
            "name": "name",
            "location": "location",
            "time": "time",
            "description": "description",
            "description_en": "description_en",
            "prompt_cn": "prompt_cn",
            "prompt_en": "prompt_en",
            "negative_prompt": "negative_prompt",
            "interpretation_cn": "interpretation_cn",
            "dialogue_count": "dialogue_count",
            "narration_count": "narration_count",
            "number": "number",
        }
        updates: dict[str, Any] = {}
        for k, col in mapping.items():
            if k in fields:
                updates[col] = fields[k]
        if "characters" in fields:
            updates["characters_json"] = json.dumps(fields["characters"], ensure_ascii=False)
        if "props" in fields:
            updates["props_json"] = json.dumps(fields["props"], ensure_ascii=False)
        if "look_states" in fields:
            updates["look_states_json"] = json.dumps(
                fields["look_states"] or {}, ensure_ascii=False, sort_keys=True
            )
        if "lines" in fields:
            lines = normalize_lines(fields["lines"])
            d_count, n_count = counts_from_lines(lines)
            updates["lines_json"] = json.dumps(lines, ensure_ascii=False)
            updates["dialogue_count"] = d_count
            updates["narration_count"] = n_count
        if not updates:
            item = self.get(project_id, scene_id)
            if not item:
                raise KeyError(scene_id)
            return item
        updates["updated_at"] = _now()
        sets = ", ".join(f"{k} = :{k}" for k in updates)
        updates["project_id"] = project_id
        updates["id"] = scene_id
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE scenes SET {sets} WHERE project_id = :project_id AND id = :id",
                updates,
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(scene_id)
        item = self.get(project_id, scene_id)
        assert item is not None
        return item
