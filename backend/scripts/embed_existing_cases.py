# ============================================
# 为已存在的 rag_cases 建立向量索引（分批编码 + 增量保存）
# 用法：
#   python -m scripts.embed_existing_cases
# ============================================
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.settings import settings  # noqa: E402
from app.db.repositories.rag_cases import RagCaseRepository  # noqa: E402
from app.services.rag_embedder import BgeEmbedder  # noqa: E402
from app.services.rag_store import RagVectorStore  # noqa: E402

CHUNK = 24


def main() -> int:
    repo = RagCaseRepository()
    store = RagVectorStore(
        persist_dir=settings.rag_chroma_dir,
        embedder=BgeEmbedder(settings.embed_model_dir),
    )
    if not store.embedder.available():
        print("[warn] bge-m3 未安装，无法建索引")
        return 1

    rows = repo.list(limit=100000)
    by_id = {r["id"]: r for r in rows}
    existing_ids = set(store._load_json().keys()) if store._backend != "chroma" else set()
    to_embed = [r for r in rows if r["id"] not in existing_ids]

    # text is not a column name: prompt is required, so rebuild doc string
    def doc_for(r: dict) -> str:
        return "\n".join(
            p for p in [r.get("title"), r.get("description"), r.get("prompt_en") or ""] if p
        )

    print(f"库中 {len(rows)} 条，已有索引 {len(existing_ids)} 条，待嵌入 {len(to_embed)} 条")
    data = store._load_json()
    t0 = time.time()
    for start in range(0, len(to_embed), CHUNK):
        chunk = to_embed[start : start + CHUNK]
        docs = [doc_for(r) for r in chunk]
        embs = store.embedder.encode(docs)
        for r, emb in zip(chunk, embs):
            data[r["id"]] = {
                "embedding": emb,
                "document": doc_for(r),
                "metadata": {"type": r.get("type"), "title": r.get("title")},
            }
        store._save_json(data)
        done = start + len(chunk)
        eta = (time.time() - t0) / done * (len(to_embed) - done) if done else 0
        print(f"[{done}/{len(to_embed)}] 已写 {len(data)} 条, 剩余约 {eta:.0f}s")
    print(f"完成：向量索引共 {len(data)} 条（耗时 {time.time()-t0:.0f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())