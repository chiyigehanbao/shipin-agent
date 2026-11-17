from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.db.connection import connect
from app.db.schema import migrate


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_asset(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["identity"] = json.loads(item.pop("identity_json", None) or "{}")
    return item


class AssetRepository:
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
        name: str,
        type: str,
        prompt_cn: str,
        prompt_en: str,
        model: str,
        negative_prompt: str = "",
        status: str = "generating",
        lock_en: str = "",
        aspect: str = "square",
        candidate_group_id: str | None = None,
        candidate_index: int | None = None,
        selection_status: str = "legacy",
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        item = {
            "id": f"asset_{type[:1]}_{uuid.uuid4().hex[:8]}",
            "project_id": project_id,
            "name": name,
            "name_en": name,
            "type": type,
            "status": status,
            "prompt_cn": prompt_cn,
            "prompt_en": prompt_en,
            "negative_prompt": negative_prompt,
            "lock_en": lock_en or "",
            "model": model,
            "aspect": aspect,
            "candidate_group_id": candidate_group_id,
            "candidate_index": candidate_index,
            "selection_status": selection_status,
            "identity_json": json.dumps(
                identity or {}, ensure_ascii=False, sort_keys=True
            ),
            "image_url": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO assets (
                  id, project_id, name, name_en, type, status, prompt_cn, prompt_en,
                  negative_prompt, lock_en, model, aspect, candidate_group_id,
                  candidate_index, selection_status, identity_json, image_url, error,
                  created_at, updated_at
                ) VALUES (
                  :id, :project_id, :name, :name_en, :type, :status, :prompt_cn, :prompt_en,
                  :negative_prompt, :lock_en, :model, :aspect, :candidate_group_id,
                  :candidate_index, :selection_status, :identity_json, :image_url, :error,
                  :created_at, :updated_at
                )
                """,
                item,
            )
            conn.commit()
        created = self.get(project_id, item["id"])
        assert created is not None
        return created

    def get(self, project_id: str, asset_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM assets WHERE project_id = ? AND id = ?",
                (project_id, asset_id),
            ).fetchone()
            return _row_to_asset(row) if row else None

    def find_by_name_type(
        self, project_id: str, type: str, name: str
    ) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM assets WHERE project_id = ? AND type = ? AND name = ? LIMIT 1",
                (project_id, type, name),
            ).fetchone()
            return _row_to_asset(row) if row else None

    def update(self, project_id: str, asset_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "name",
            "name_en",
            "type",
            "status",
            "prompt_cn",
            "prompt_en",
            "negative_prompt",
            "lock_en",
            "model",
            "aspect",
            "candidate_group_id",
            "candidate_index",
            "selection_status",
            "image_url",
            "error",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if "identity" in fields:
            updates["identity_json"] = json.dumps(
                fields["identity"] or {}, ensure_ascii=False, sort_keys=True
            )
        updates["updated_at"] = _now()
        sets = ", ".join(f"{k} = :{k}" for k in updates)
        updates["project_id"] = project_id
        updates["id"] = asset_id
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE assets SET {sets} WHERE project_id = :project_id AND id = :id",
                updates,
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(asset_id)
        item = self.get(project_id, asset_id)
        assert item is not None
        return item

    def list(self, project_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM assets WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
            return [_row_to_asset(r) for r in rows]

    def list_by_status(self, status: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM assets
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
            return [_row_to_asset(r) for r in rows]

    def queue_depth(self) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM assets WHERE status = 'generating'"
            ).fetchone()
            return int(row["c"])
