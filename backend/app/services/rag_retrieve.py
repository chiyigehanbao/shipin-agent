from __future__ import annotations

from typing import Any

from app.core.settings import settings
from app.db.repositories.rag_cases import RagCaseRepository
from app.services.rag_embedder import BgeEmbedder
from app.services.rag_store import RagVectorStore

_repo: RagCaseRepository | None = None
_store: RagVectorStore | None = None


def get_rag_repo() -> RagCaseRepository:
    global _repo
    if _repo is None:
        _repo = RagCaseRepository()
    return _repo


def get_rag_store() -> RagVectorStore:
    global _store
    if _store is None:
        _store = RagVectorStore(
            persist_dir=settings.rag_chroma_dir,
            embedder=BgeEmbedder(settings.embed_model_dir),
        )
    return _store


def set_rag_backends(
    repo: RagCaseRepository | None = None,
    store: RagVectorStore | None = None,
) -> None:
    """Test hook to inject FakeEmbedder-backed store."""
    global _repo, _store
    if repo is not None:
        _repo = repo
    if store is not None:
        _store = store


def format_rag_block(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return ""
    parts = ["参考案例（仅风格与结构，勿照抄）:"]
    for h in hits:
        case = h.get("case") or {}
        title = case.get("title") or h.get("id") or ""
        desc = case.get("description") or ""
        prompt = case.get("prompt_en") or ""
        chunk = f"【{title}】\n{desc}"
        if prompt:
            chunk += f"\nprompt_en: {prompt[:400]}"
        parts.append(chunk)
    return "\n---\n".join(parts)


def _keyword_fallback(query: str, *, top_k: int, type_filter: str | None) -> list[dict[str, Any]]:
    """Vector-free fallback: SQL keyword search across title/description/prompt_en."""
    repo = get_rag_repo()
    try:
        rows = repo.search(query=query, type=type_filter, limit=top_k)
    except Exception:
        return []
    hits = []
    for r in rows:
        try:
            repo.increment_usage(r["id"])
        except Exception:
            pass
        hits.append({"case": r, "similarity": 1.0})
    return hits


def build_rag_context(query: str, *, top_k: int = 3, type_filter: str | None = None) -> str:
    query = (query or "").strip()
    if not query:
        return ""
    try:
        store = get_rag_store()
        if not store.embedder.available():
            hits = _keyword_fallback(query, top_k=top_k, type_filter=type_filter)
            return format_rag_block(hits)
        hits_raw = store.query(query, top_k=top_k, type_filter=type_filter)
    except Exception:
        return _keyword_fallback(query, top_k=top_k, type_filter=type_filter)
    if not hits_raw:
        return ""
    repo = get_rag_repo()
    hits = []
    for h in hits_raw:
        case = repo.get(h["id"])
        if not case:
            continue
        try:
            repo.increment_usage(case["id"])
        except Exception:
            pass
        hits.append({"case": case, "similarity": h.get("similarity", 0)})
    return format_rag_block(hits)
