from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.services.rag_embedder import EmbedderProto


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(0.0, min(1.0, dot / (na * nb)))


class RagVectorStore:
    """
    Vector index for RAG cases.
    Prefer Chroma when installed; otherwise persist JSON embeddings under persist_dir.
    Collection name kept as vf_cases for Chroma path.
    """

    def __init__(
        self,
        *,
        persist_dir: Path,
        embedder: EmbedderProto,
        collection_name: str = "vf_cases",
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.embedder = embedder
        self.collection_name = collection_name
        self._collection = None
        self._backend = None  # "chroma" | "json"
        self._json_path = self.persist_dir / "vf_cases.json"

    def _ensure(self) -> str:
        if self._backend:
            return self._backend
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(self.persist_dir / "chroma"))
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._backend = "chroma"
        except Exception:
            if not self._json_path.exists():
                self._json_path.write_text("{}", encoding="utf-8")
            self._backend = "json"
        return self._backend

    def _load_json(self) -> dict[str, Any]:
        self._ensure()
        try:
            return json.loads(self._json_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_json(self, data: dict[str, Any]) -> None:
        self._json_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def upsert(
        self,
        *,
        case_id: str,
        document: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        emb = self.embedder.encode([document])[0]
        meta = {k: ("" if v is None else v) for k, v in (metadata or {}).items()}
        clean = {}
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool)):
                clean[k] = v
            else:
                clean[k] = str(v)
        backend = self._ensure()
        if backend == "chroma":
            self._collection.upsert(
                ids=[case_id],
                embeddings=[emb],
                documents=[document],
                metadatas=[clean],
            )
            return
        data = self._load_json()
        data[case_id] = {
            "embedding": emb,
            "document": document,
            "metadata": clean,
        }
        self._save_json(data)

    def upsert_many(
        self,
        *,
        items: list[dict[str, Any]],
    ) -> None:
        """Batch upsert for the JSON backend.

        Each item: {"case_id", "document", "metadata"}. Encodes all documents in
        one call and persists once, avoiding O(n^2) full-file rewrites.
        For the chroma backend this transparently falls back to per-item upsert.
        """
        if not items:
            return
        docs = [str(i["document"]) for i in items]
        embs = self.embedder.encode(docs)
        backend = self._ensure()
        if backend == "chroma":
            ids = [str(i["case_id"]) for i in items]
            metas = [
                {
                    k: ("" if v is None else v)
                    for k, v in (i.get("metadata") or {}).items()
                    if isinstance(v, (str, int, float, bool)) or v is None
                }
                for i in items
            ]
            self._collection.upsert(
                ids=ids,
                embeddings=embs,
                documents=docs,
                metadatas=metas,
            )
            return
        data = self._load_json()
        for i, emb in zip(items, embs):
            data[str(i["case_id"])] = {
                "embedding": emb,
                "document": str(i["document"]),
                "metadata": dict((i.get("metadata") or {})),
            }
        self._save_json(data)

    def delete(self, case_id: str) -> None:
        backend = self._ensure()
        if backend == "chroma":
            try:
                self._collection.delete(ids=[case_id])
            except Exception:
                pass
            return
        data = self._load_json()
        if case_id in data:
            del data[case_id]
            self._save_json(data)

    def query(
        self,
        query: str,
        *,
        top_k: int = 5,
        type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        if not (query or "").strip():
            return []
        emb = self.embedder.encode([query])[0]
        backend = self._ensure()
        if backend == "chroma":
            kwargs: dict[str, Any] = {
                "query_embeddings": [emb],
                "n_results": max(1, top_k),
                "include": ["documents", "metadatas", "distances"],
            }
            if type_filter:
                kwargs["where"] = {"type": type_filter}
            res = self._collection.query(**kwargs)
            ids = (res.get("ids") or [[]])[0]
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            out = []
            for i, cid in enumerate(ids):
                dist = float(dists[i]) if i < len(dists) else 1.0
                sim = max(0.0, 1.0 - dist)
                out.append(
                    {
                        "id": cid,
                        "document": docs[i] if i < len(docs) else "",
                        "metadata": metas[i] if i < len(metas) else {},
                        "similarity": sim,
                    }
                )
            return out

        data = self._load_json()
        scored = []
        for cid, row in data.items():
            meta = row.get("metadata") or {}
            if type_filter and meta.get("type") != type_filter:
                continue
            sim = _cosine(emb, row.get("embedding") or [])
            scored.append(
                {
                    "id": cid,
                    "document": row.get("document") or "",
                    "metadata": meta,
                    "similarity": sim,
                }
            )
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[: max(1, top_k)] if scored else []
