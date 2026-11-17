from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.db.connection import connect
from app.db.schema import migrate
from app.services.script_lines import normalize_lines


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_frame(row: dict[str, Any]) -> dict[str, Any]:
    lines = normalize_lines(json.loads(row.get("lines_json") or "[]"))
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "number": row["number"],
        "description": row.get("description") or "",
        "description_en": row.get("description_en") or "",
        "character": row.get("character") or "",
        "scene": row.get("scene") or "",
        "scene_id": row.get("scene_id"),
        "shot_type": row.get("shot_type") or "中景",
        "angle": row.get("angle") or "平视",
        "movement": row.get("movement") or "固定",
        "duration": row.get("duration") if row.get("duration") is not None else 3.0,
        "prompt_cn": row.get("prompt_cn") or "",
        "prompt_en": row.get("prompt_en") or "",
        "negative_prompt": row.get("negative_prompt") or "",
        "motion_prompt_en": row.get("motion_prompt_en") or "",
        "status": row.get("status") or "pending",
        "image_url": row.get("image_url"),
        "asset_id": row.get("asset_id"),
        "accepted_render_attempt_id": row.get("accepted_render_attempt_id"),
        "model": row.get("model") or "flux",
        "error": row.get("error"),
        "video_url": row.get("video_url"),
        "video_status": row.get("video_status") or "pending",
        "video_error": row.get("video_error"),
        "video_job_id": row.get("video_job_id"),
        "lines": lines,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


class FrameRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self):
        return connect(self.db_path)

    def list(self, project_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM storyboard_frames WHERE project_id = ? ORDER BY number ASC",
                (project_id,),
            ).fetchall()
            return [_row_to_frame(dict(r)) for r in rows]

    def get(self, project_id: str, frame_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM storyboard_frames WHERE project_id = ? AND id = ?",
                (project_id, frame_id),
            ).fetchone()
            return _row_to_frame(dict(row)) if row else None

    def create(self, project_id: str, **fields: Any) -> dict[str, Any]:
        now = _now()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(number), 0) AS m FROM storyboard_frames WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            number = int(row["m"]) + 1
            frame_id = fields.pop("id", None) or f"frame_{uuid.uuid4().hex[:8]}"
            lines = normalize_lines(fields.pop("lines", None) or [])
            item = {
                "id": frame_id,
                "project_id": project_id,
                "number": number,
                "description": "",
                "description_en": "",
                "character": "",
                "scene": "",
                "scene_id": None,
                "shot_type": "中景",
                "angle": "平视",
                "movement": "固定",
                "duration": 3.0,
                "prompt_cn": "",
                "prompt_en": "",
                "negative_prompt": "",
                "motion_prompt_en": "",
                "status": "pending",
                "image_url": None,
                "asset_id": None,
                "accepted_render_attempt_id": None,
                "model": "flux",
                "error": None,
                "video_url": None,
                "video_status": "pending",
                "video_error": None,
                "video_job_id": None,
                "lines_json": json.dumps(lines, ensure_ascii=False),
                "created_at": now,
                "updated_at": now,
            }
            item.update(fields)
            if "lines" in item:
                lines = normalize_lines(item.pop("lines"))
                item["lines_json"] = json.dumps(lines, ensure_ascii=False)
            item["id"] = frame_id
            item["project_id"] = project_id
            item["number"] = number
            item["created_at"] = now
            item["updated_at"] = now
            if "lines_json" not in item:
                item["lines_json"] = json.dumps([], ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO storyboard_frames (
                  id, project_id, number, description, description_en, character, scene,
                  scene_id, shot_type, angle, movement, duration, prompt_cn, prompt_en,
                  negative_prompt, motion_prompt_en, status, image_url, asset_id,
                  accepted_render_attempt_id, model, error, lines_json,
                  video_url, video_status, video_error, video_job_id,
                  created_at, updated_at
                ) VALUES (
                  :id, :project_id, :number, :description, :description_en, :character, :scene,
                  :scene_id, :shot_type, :angle, :movement, :duration, :prompt_cn, :prompt_en,
                  :negative_prompt, :motion_prompt_en, :status, :image_url, :asset_id,
                  :accepted_render_attempt_id, :model, :error, :lines_json,
                  :video_url, :video_status, :video_error, :video_job_id,
                  :created_at, :updated_at
                )
                """,
                item,
            )
            conn.commit()
        return self.get(project_id, frame_id)

    def update(self, project_id: str, frame_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "number",
            "description",
            "description_en",
            "character",
            "scene",
            "scene_id",
            "shot_type",
            "angle",
            "movement",
            "duration",
            "prompt_cn",
            "prompt_en",
            "negative_prompt",
            "motion_prompt_en",
            "status",
            "image_url",
            "asset_id",
            "accepted_render_attempt_id",
            "model",
            "error",
            "video_url",
            "video_status",
            "video_error",
            "video_job_id",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if "lines" in fields:
            lines = normalize_lines(fields["lines"])
            updates["lines_json"] = json.dumps(lines, ensure_ascii=False)
        updates["updated_at"] = _now()
        sets = ", ".join(f"{k} = :{k}" for k in updates)
        updates["project_id"] = project_id
        updates["id"] = frame_id
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE storyboard_frames SET {sets} WHERE project_id = :project_id AND id = :id",
                updates,
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(frame_id)
        item = self.get(project_id, frame_id)
        assert item is not None
        return item

    def list_by_status(self, status: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM storyboard_frames WHERE status = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (status, limit),
            ).fetchall()
            return [_row_to_frame(dict(r)) for r in rows]

    def list_by_video_status(
        self, video_status: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM storyboard_frames WHERE video_status = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (video_status, limit),
            ).fetchall()
            return [_row_to_frame(dict(r)) for r in rows]

    def delete_by_scene(self, project_id: str, scene_id: str, *, only_without_image: bool = False) -> int:
        with self._conn() as conn:
            if only_without_image:
                cur = conn.execute(
                    """
                    DELETE FROM storyboard_frames
                    WHERE project_id = ? AND scene_id = ?
                      AND (image_url IS NULL OR image_url = '')
                    """,
                    (project_id, scene_id),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM storyboard_frames WHERE project_id = ? AND scene_id = ?",
                    (project_id, scene_id),
                )
            conn.commit()
            return int(cur.rowcount or 0)

    def delete(self, project_id: str, frame_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM storyboard_frames WHERE project_id = ? AND id = ?",
                (project_id, frame_id),
            )
            conn.commit()
            return int(cur.rowcount or 0) > 0
