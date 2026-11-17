from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.db.connection import connect
from app.db.schema import migrate


LEGAL_TRANSITIONS = {
    "queued": {"running", "failed"},
    "running": {"candidate", "failed"},
    "candidate": {"accepted", "rejected"},
    "accepted": {"superseded"},
    "superseded": set(),
    "rejected": set(),
    "failed": set(),
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _assert_transition(current: str, target: str) -> None:
    if target not in LEGAL_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid_attempt_transition:{current}->{target}")


def _request_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["request"] = json.loads(item.pop("request_json") or "{}")
    item["validation"] = json.loads(item.pop("validation_json") or "{}")
    return item


def _attempt_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["error"] = json.loads(item.pop("error_json") or "{}")
    item["identity_evaluation"] = json.loads(
        item.pop("identity_evaluation_json", None) or "{}"
    )
    item["is_degraded"] = bool(item["is_degraded"])
    return item


class _Repository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)


class RenderRequestRepository(_Repository):
    def create(
        self,
        *,
        project_id: str,
        frame_id: str,
        source_hash: str,
        request: dict[str, Any],
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = f"rr_{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO storyboard_render_requests (
                  id, project_id, frame_id, source_hash, request_json,
                  validation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    project_id,
                    frame_id,
                    source_hash,
                    _json(request),
                    _json(validation),
                    _now(),
                ),
            )
            conn.commit()
        item = self.get(request_id)
        assert item is not None
        return item

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM storyboard_render_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        return _request_row(row) if row else None

    def latest_for_frame(
        self, project_id: str, frame_id: str
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM storyboard_render_requests
                WHERE project_id = ? AND frame_id = ?
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (project_id, frame_id),
            ).fetchone()
        return _request_row(row) if row else None


class RenderAttemptRepository(_Repository):
    def create(
        self,
        *,
        request_id: str,
        project_id: str,
        frame_id: str,
        adapter: str,
        workflow_version: str,
        model_fingerprint: str,
        seed: int,
        is_degraded: bool,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        attempt_id = f"ra_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO storyboard_render_attempts (
                  id, request_id, project_id, frame_id, asset_id, adapter,
                  workflow_version, model_fingerprint, seed, is_degraded,
                  status, error_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', '{}', ?, ?)
                """,
                (
                    attempt_id,
                    request_id,
                    project_id,
                    frame_id,
                    asset_id,
                    adapter,
                    workflow_version,
                    model_fingerprint,
                    seed,
                    int(is_degraded),
                    now,
                    now,
                ),
            )
            conn.commit()
        item = self.get(attempt_id)
        assert item is not None
        return item

    def get(self, attempt_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM storyboard_render_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()
        return _attempt_row(row) if row else None

    def list_for_frame(self, project_id: str, frame_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM storyboard_render_attempts
                WHERE project_id = ? AND frame_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (project_id, frame_id),
            ).fetchall()
        return [_attempt_row(row) for row in rows]

    def transition(
        self,
        attempt_id: str,
        status: str,
        *,
        image_url: str | None = None,
        error: dict[str, Any] | str | None = None,
        rejection_reason: str | None = None,
        rejection_note: str | None = None,
    ) -> dict[str, Any]:
        current = self.get(attempt_id)
        if current is None:
            raise KeyError(attempt_id)
        _assert_transition(current["status"], status)
        now = _now()
        error_value = current["error"]
        if isinstance(error, str):
            error_value = {"code": error}
        elif error is not None:
            error_value = error
        started_at = now if status == "running" else current["started_at"]
        finished_at = (
            now
            if status in {"candidate", "accepted", "superseded", "rejected", "failed"}
            else current["finished_at"]
        )
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE storyboard_render_attempts
                SET status = ?, image_url = ?, error_json = ?,
                    rejection_reason = ?, rejection_note = ?, started_at = ?,
                    finished_at = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    status,
                    image_url if image_url is not None else current["image_url"],
                    _json(error_value),
                    rejection_reason
                    if rejection_reason is not None
                    else current["rejection_reason"],
                    rejection_note
                    if rejection_note is not None
                    else current["rejection_note"],
                    started_at,
                    finished_at,
                    now,
                    attempt_id,
                    current["status"],
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise RuntimeError(f"attempt_status_changed:{attempt_id}")
        item = self.get(attempt_id)
        assert item is not None
        return item

    def attach_job(self, attempt_id: str, job_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE storyboard_render_attempts
                SET job_id = ?, updated_at = ? WHERE id = ?
                """,
                (job_id, _now(), attempt_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(attempt_id)
        item = self.get(attempt_id)
        assert item is not None
        return item

    def set_identity_evaluation(
        self, attempt_id: str, evaluation: dict[str, Any]
    ) -> dict[str, Any]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE storyboard_render_attempts
                SET identity_evaluation_json = ?, updated_at = ? WHERE id = ?
                """,
                (_json(evaluation), _now(), attempt_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(attempt_id)
        item = self.get(attempt_id)
        assert item is not None
        return item

    def fail_inflight(self, *, error: dict[str, Any] | str) -> int:
        error_value = {"code": error} if isinstance(error, str) else error
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE storyboard_render_attempts
                SET status = 'failed', error_json = ?, finished_at = ?, updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (_json(error_value), now, now),
            )
            conn.commit()
            return int(cur.rowcount)
