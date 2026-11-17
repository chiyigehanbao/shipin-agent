from pathlib import Path

from app.db.connection import connect
from app.db.repositories.rag_cases import RagCaseRepository
from app.db.schema import migrate
from app.services.rag_embedder import FakeEmbedder
from app.services.rag_retrieve import build_rag_context, format_rag_block, set_rag_backends
from app.services.rag_store import RagVectorStore


def test_upsert_and_query(tmp_path: Path):
    db = tmp_path / "rag.db"
    migrate(connect(db))
    repo = RagCaseRepository(db)
    store = RagVectorStore(
        persist_dir=tmp_path / "chroma",
        embedder=FakeEmbedder(),
    )
    a = repo.create(
        title="赛博夜景",
        type="scene",
        description="霓虹街道雨夜",
        prompt_en="cyberpunk rainy street",
    )
    b = repo.create(
        title="古风庭院",
        type="scene",
        description="月下青砖庭院",
        prompt_en="ancient courtyard moonlight",
    )
    store.upsert(
        case_id=a["id"],
        document=f"{a['title']}\n{a['description']}\n{a['prompt_en']}",
        metadata={"type": "scene", "title": a["title"]},
    )
    store.upsert(
        case_id=b["id"],
        document=f"{b['title']}\n{b['description']}\n{b['prompt_en']}",
        metadata={"type": "scene", "title": b["title"]},
    )
    hits = store.query("霓虹雨夜赛博朋克", top_k=2)
    assert len(hits) >= 1
    assert hits[0]["id"] in {a["id"], b["id"]}


def test_empty_query_returns_empty(tmp_path: Path):
    store = RagVectorStore(persist_dir=tmp_path / "chroma2", embedder=FakeEmbedder())
    assert store.query("", top_k=3) == []


def test_build_rag_context_injects(tmp_path: Path):
    db = tmp_path / "rag.db"
    migrate(connect(db))
    repo = RagCaseRepository(db)
    store = RagVectorStore(persist_dir=tmp_path / "chroma3", embedder=FakeEmbedder())
    set_rag_backends(repo=repo, store=store)
    c = repo.create(
        title="短剧开场",
        type="storyboard",
        description="黄金三秒镜头",
        prompt_en="cold open whip pan",
    )
    store.upsert(
        case_id=c["id"],
        document=f"{c['title']}\n{c['description']}",
        metadata={"type": "storyboard", "title": c["title"]},
    )
    block = build_rag_context("短剧开场镜头", top_k=2)
    assert "参考案例" in block
    assert "短剧开场" in block


def test_format_rag_block_empty():
    assert format_rag_block([]) == ""


def test_keyword_fallback_when_no_embedder(tmp_path: Path):
    db = tmp_path / "rag.db"
    migrate(connect(db))
    repo = RagCaseRepository(db)

    class NoEmbedder(FakeEmbedder):
        def available(self) -> bool:
            return False

    store = RagVectorStore(persist_dir=tmp_path / "chroma4", embedder=NoEmbedder())
    set_rag_backends(repo=repo, store=store)
    repo.create(
        title="赛博雨夜",
        type="scene",
        description="霓虹街道雨夜",
        prompt_en="cyberpunk rainy street neon",
    )
    repo.create(
        title="古风庭院",
        type="scene",
        description="月下青砖庭院",
        prompt_en="ancient courtyard moonlight",
    )
    repo.create(
        title="收银台商品特写",
        type="prop",
        description="饮料瓶贴标旋转",
        prompt_en="soda bottle rotating on counter",
    )

    block = build_rag_context("霓虹雨夜赛博朋克街道", top_k=2)
    assert "参考案例" in block
    assert "赛博雨夜" in block

    filtered = build_rag_context("饮料瓶", top_k=2, type_filter="prop")
    assert "收银台商品特写" in filtered
    assert "赛博雨夜" not in filtered

    assert build_rag_context("") == ""
