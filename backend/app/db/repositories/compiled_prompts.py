from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.db.connection import connect
from app.db.schema import migrate


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def _row(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["validation_json"] = json.loads(item.get("validation_json") or "{}")
    item["is_user_edited"] = bool(item.get("is_user_edited"))
    return item


class CompiledPromptRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self):
        return connect(self.db_path)

    def create(
        self,
        *,
        project_id: str,
        source_type: str,
        source_id: str,
        target_model: str,
        mode: str,
        source_hash: str,
        guide_version: str,
        content: str,
        validation: dict[str, Any],
        provider: str,
        status: str = "draft",
        is_user_edited: bool = False,
    ) -> dict[str, Any]:
        prompt_id = f"cp_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO compiled_prompts (
                  id, project_id, source_type, source_id, target_model, mode,
                  source_hash, guide_version, content, validation_json, provider,
                  status, is_user_edited, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_id,
                    project_id,
                    source_type,
                    source_id,
                    target_model,
                    mode,
                    source_hash,
                    guide_version,
                    content,
                    json.dumps(validation, ensure_ascii=False, separators=(",", ":")),
                    provider,
                    status,
                    int(is_user_edited),
                    now,
                    now,
                ),
            )
            conn.commit()
        item = self.get(prompt_id)
        assert item is not None
        return item

    def get(self, prompt_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM compiled_prompts WHERE id = ?", (prompt_id,)
            ).fetchone()
            return _row(row) if row else None

    def latest(
        self, project_id: str, source_type: str, source_id: str, mode: str
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM compiled_prompts
                WHERE project_id = ? AND source_type = ? AND source_id = ? AND mode = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (project_id, source_type, source_id, mode),
            ).fetchone()
            return _row(row) if row else None

    def update(self, prompt_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"content", "validation_json", "status", "is_user_edited"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if "validation_json" in updates and isinstance(updates["validation_json"], dict):
            updates["validation_json"] = json.dumps(
                updates["validation_json"], ensure_ascii=False, separators=(",", ":")
            )
        if "is_user_edited" in updates:
            updates["is_user_edited"] = int(bool(updates["is_user_edited"]))
        if not updates:
            item = self.get(prompt_id)
            if item is None:
                raise KeyError(prompt_id)
            return item
        updates["updated_at"] = _now()
        updates["id"] = prompt_id
        sets = ", ".join(f"{key} = :{key}" for key in updates if key != "id")
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE compiled_prompts SET {sets} WHERE id = :id", updates
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(prompt_id)
        item = self.get(prompt_id)
        assert item is not None
        return item
