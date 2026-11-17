# ============================================
# 项目完成时自动沉淀经验到 RAG 知识库（best-effort）
# ============================================
from __future__ import annotations

from typing import Any

from app.services.rag_retrieve import get_rag_repo, get_rag_store


def _embed_doc(case: dict[str, Any]) -> str:
    parts = [
        case.get("title") or "",
        case.get("description") or "",
        case.get("prompt_en") or "",
        " ".join(case.get("tags") or []),
    ]
    return "\n".join(p for p in parts if p)


def _embedder_ok() -> bool:
    try:
        store = get_rag_store()
        return bool(store and store.embedder.available())
    except Exception:
        return False


def auto_ingest_project(project_id: str) -> dict[str, int]:
    """把项目的场景 / 角色·场景资产 / 分镜提示词沉淀为 RAG 案例。"""
    from app.db.repositories.scenes import SceneRepository
    from app.services.runtime import storyboard_store, store as asset_store

    repo = get_rag_repo()
    embed_ok = _embedder_ok()
    counts: dict[str, int] = {"scene": 0, "character": 0, "prop": 0, "storyboard": 0, "total": 0}

    def _add(ctype: str, title: str, description: str, prompt_en: str, negative: str, ref: str) -> None:
        if not (prompt_en or "").strip():
            return
        case = repo.create(
            title=title,
            type=ctype if ctype in ("scene", "character", "prop", "storyboard") else "scene",
            style="",
            description=description,
            tags=[],
            prompt_en=prompt_en,
            negative_prompt=negative,
            source_project_id=project_id,
            source_ref=ref,
        )
        if embed_ok:
            try:
                get_rag_store().upsert(
                    case_id=case["id"],
                    document=_embed_doc(case),
                    metadata={"type": case["type"], "title": case["title"]},
                )
            except Exception:
                repo.delete(case["id"])
                return
        counts[ctype] += 1
        counts["total"] += 1

    # 场景
    try:
        scenes = SceneRepository().list_by_project(project_id)
        for s in scenes:
            _add(
                "scene",
                s.get("name") or "场景",
                s.get("description") or "",
                s.get("prompt_en") or "",
                s.get("negative_prompt") or "",
                f"scene:{s['id']}",
            )
    except Exception:
        pass

    # 角色 / 场景 / 道具资产
    try:
        assets = asset_store.list(project_id)
        for a in assets:
            t = a.get("type") or "character"
            if t not in ("character", "scene", "prop"):
                continue
            _add(
                t,
                a.get("name") or "资产",
                a.get("prompt_cn") or "",
                a.get("prompt_en") or "",
                a.get("negative_prompt") or "",
                f"asset:{a['id']}",
            )
    except Exception:
        pass

    # 分镜帧
    try:
        frames = storyboard_store.list(project_id)
        for f in frames:
            _add(
                "storyboard",
                f"分镜 {f.get('number') or ''}",
                f.get("description") or "",
                f.get("prompt_en") or "",
                f.get("negative_prompt") or "",
                f"frame:{f['id']}",
            )
    except Exception:
        pass

    return counts
