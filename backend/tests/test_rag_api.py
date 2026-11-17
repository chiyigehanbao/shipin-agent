from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.connection import connect
from app.db.repositories.rag_cases import RagCaseRepository
from app.db.schema import migrate
from app.main import app
from app.services.rag_embedder import FakeEmbedder
from app.services.rag_retrieve import set_rag_backends
from app.services.rag_store import RagVectorStore


def _setup(tmp_path: Path):
    db = tmp_path / "rag_api.db"
    migrate(connect(db))
    repo = RagCaseRepository(db)
    store = RagVectorStore(persist_dir=tmp_path / "chroma", embedder=FakeEmbedder())
    set_rag_backends(repo=repo, store=store)
    return repo, store


def test_rag_api_crud_and_search(tmp_path: Path):
    repo, store = _setup(tmp_path)
    client = TestClient(app)
    with patch("app.api.rag.get_rag_repo", return_value=repo), patch(
        "app.api.rag.get_rag_store", return_value=store
    ), patch("app.api.rag._require_embedder", return_value=store):
        r = client.post(
            "/api/rag/cases",
            json={
                "title": "修真主角",
                "type": "character",
                "description": "多角度",
                "prompt_en": "xianxia protagonist",
                "tags": ["修真"],
            },
        )
        assert r.status_code == 200
        cid = r.json()["id"]

        r2 = client.get("/api/rag/cases")
        assert r2.status_code == 200
        assert any(c["id"] == cid for c in r2.json())

        r3 = client.post(
            "/api/rag/search",
            json={"query": "修真主角多角度", "top_k": 3},
        )
        assert r3.status_code == 200
        assert len(r3.json()) >= 1

        r4 = client.get("/api/rag/stats")
        assert r4.status_code == 200
        assert r4.json()["total"] >= 1

        r5 = client.delete(f"/api/rag/cases/{cid}")
        assert r5.status_code == 200


def test_search_empty_library(tmp_path: Path):
    repo, store = _setup(tmp_path)
    client = TestClient(app)
    with patch("app.api.rag.get_rag_repo", return_value=repo), patch(
        "app.api.rag.get_rag_store", return_value=store
    ), patch("app.api.rag._require_embedder", return_value=store):
        r = client.post("/api/rag/search", json={"query": "anything", "top_k": 3})
        assert r.status_code == 200
        assert r.json() == []
