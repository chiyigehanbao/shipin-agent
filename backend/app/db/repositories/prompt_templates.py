from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.db.connection import connect
from app.db.schema import migrate

_COLS = [
    "id",
    "name",
    "name_en",
    "category",
    "category_name",
    "version",
    "usage_count",
    "updated_at",
    "system_prompt_cn",
    "system_prompt_en",
    "user_prompt_cn",
    "user_prompt_en",
    "negative_prompt_cn",
    "negative_prompt_en",
    "default_steps",
    "default_cfg",
    "default_sampler",
    "default_scheduler",
    "default_model",
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    return {k: d.get(k) for k in _COLS}


class PromptTemplateRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self):
        return connect(self.db_path)

    def list_all(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {', '.join(_COLS)} FROM prompt_templates"
            ).fetchall()
            return [_row_to_dict(r) for r in rows]

    def get(self, template_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {', '.join(_COLS)} FROM prompt_templates WHERE id = ?",
                (template_id,),
            ).fetchone()
            return _row_to_dict(row) if row else None

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        tpl_id = data.get("id") or f"tpl_{uuid.uuid4().hex[:8]}"
        defaults: dict[str, Any] = {
            "name": "",
            "name_en": "",
            "category": "",
            "category_name": "",
            "version": "",
            "usage_count": 0,
            "updated_at": _now(),
            "system_prompt_cn": "",
            "system_prompt_en": "",
            "user_prompt_cn": "",
            "user_prompt_en": "",
        }
        item = {k: data.get(k, defaults.get(k)) for k in _COLS}
        item["id"] = tpl_id
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO prompt_templates ({', '.join(_COLS)}) "
                f"VALUES ({', '.join('?' * len(_COLS))})",
                [item[c] for c in _COLS],
            )
            conn.commit()
        return self.get(tpl_id) or item

    def update(self, template_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sets = [f"{c}=?" for c in _COLS if c in data]
        if not sets:
            return self.get(template_id)
        vals = [data[c] for c in _COLS if c in data]
        vals.append(template_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE prompt_templates SET {', '.join(sets)} WHERE id = ?", vals
            )
            conn.commit()
        return self.get(template_id)

    def delete(self, template_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM prompt_templates WHERE id = ?", (template_id,)
            )
            conn.commit()
            return int(cur.rowcount or 0) > 0
