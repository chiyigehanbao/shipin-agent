from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.db.connection import connect
from app.db.schema import migrate


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row(r: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(r)
    d["payload"] = json.loads(d.pop("payload_json") or "{}")
    d["result"] = json.loads(d.pop("result_json") or "{}")
    return d


class JobRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def create(
        self,
        *,
        type: str,
        project_id: str | None,
        title: str,
        payload: dict,
        link_path: str | None = None,
    ) -> dict[str, Any]:
        jid = f"job_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO jobs
                (id, type, project_id, status, progress, title, payload_json, result_json, error, link_path, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    jid,
                    type,
                    project_id,
                    "queued",
                    0,
                    title,
                    json.dumps(payload, ensure_ascii=False),
                    "{}",
                    None,
                    link_path,
                    now,
                ),
            )
            conn.commit()
        got = self.get(jid)
        assert got is not None
        return got

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _row(row) if row else None

    def update(self, job_id: str, **fields: Any) -> Optional[dict[str, Any]]:
        allowed = {
            "status",
            "progress",
            "title",
            "error",
            "link_path",
            "started_at",
            "finished_at",
        }
        cols: list[str] = []
        vals: list[Any] = []
        if "payload" in fields:
            cols.append("payload_json=?")
            vals.append(json.dumps(fields.pop("payload"), ensure_ascii=False))
        if "result" in fields:
            cols.append("result_json=?")
            vals.append(json.dumps(fields.pop("result"), ensure_ascii=False))
        for k, v in list(fields.items()):
            if k not in allowed:
                continue
            cols.append(f"{k}=?")
            vals.append(v)
        if not cols:
            return self.get(job_id)
        vals.append(job_id)
        with self._conn() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(cols)} WHERE id=?", vals)
            conn.commit()
        return self.get(job_id)

    def list_active(
        self, *, project_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM jobs WHERE status IN ('queued','running')"
        args: list[Any] = []
        if project_id:
            q += " AND project_id=?"
            args.append(project_id)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as conn:
            rows = conn.execute(q, args).fetchall()
        return [_row(r) for r in rows]

    def list_recent_failed(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM jobs WHERE status='failed'
                   ORDER BY COALESCE(finished_at, created_at) DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [_row(r) for r in rows]

    def fail_stale(self, *, error: str = "server_restarted") -> int:
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE jobs SET status='failed', error=?, finished_at=?
                   WHERE status IN ('queued','running')""",
                (error, now),
            )
            conn.commit()
            return int(cur.rowcount)

    def find_active_by_asset(self, asset_id: str) -> Optional[dict[str, Any]]:
        for j in self.list_active(limit=200):
            payload = j.get("payload") or {}
            if payload.get("asset_id") == asset_id:
                return j
        return None
