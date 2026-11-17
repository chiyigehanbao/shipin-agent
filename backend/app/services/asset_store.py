# ============================================
# 资产生成状态存储（SQLite）
# ============================================
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.db.repositories.assets import AssetRepository


class AssetStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._repo = AssetRepository(db_path)

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
        return self._repo.create(
            project_id=project_id,
            name=name,
            type=type,
            prompt_cn=prompt_cn,
            prompt_en=prompt_en,
            model=model,
            negative_prompt=negative_prompt,
            status=status,
            lock_en=lock_en,
            aspect=aspect,
            candidate_group_id=candidate_group_id,
            candidate_index=candidate_index,
            selection_status=selection_status,
            identity=identity,
        )

    def get(self, project_id: str, asset_id: str) -> Optional[dict[str, Any]]:
        return self._repo.get(project_id, asset_id)

    def find_by_name_type(
        self, project_id: str, type: str, name: str
    ) -> Optional[dict[str, Any]]:
        return self._repo.find_by_name_type(project_id, type, name)

    def update(self, project_id: str, asset_id: str, **fields: Any) -> dict[str, Any]:
        return self._repo.update(project_id, asset_id, **fields)

    def list(self, project_id: str) -> list[dict[str, Any]]:
        return self._repo.list(project_id)

    def list_by_status(self, status: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return self._repo.list_by_status(status, limit=limit)

    def queue_depth(self) -> int:
        return self._repo.queue_depth()
