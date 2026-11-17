# ============================================
# 分镜帧状态存储（SQLite）
# ============================================
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.db.repositories.frames import FrameRepository


class StoryboardStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._repo = FrameRepository(db_path)

    def ensure_seeded(self, project_id: str) -> None:
        # 默认不插入演示帧；空项目返回空列表
        return None

    def list(self, project_id: str) -> list[dict[str, Any]]:
        self.ensure_seeded(project_id)
        return self._repo.list(project_id)

    def get(self, project_id: str, frame_id: str) -> Optional[dict[str, Any]]:
        self.ensure_seeded(project_id)
        return self._repo.get(project_id, frame_id)

    def update(self, project_id: str, frame_id: str, **fields: Any) -> dict[str, Any]:
        self.ensure_seeded(project_id)
        return self._repo.update(project_id, frame_id, **fields)

    def create(self, project_id: str, **fields: Any) -> dict[str, Any]:
        self.ensure_seeded(project_id)
        return self._repo.create(project_id, **fields)

    def delete(self, project_id: str, frame_id: str) -> bool:
        return self._repo.delete(project_id, frame_id)

    def list_by_status(self, status: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return self._repo.list_by_status(status, limit=limit)

    def list_by_video_status(
        self, video_status: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        return self._repo.list_by_video_status(video_status, limit=limit)
