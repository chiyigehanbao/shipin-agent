from pathlib import Path

from app.db.connection import connect
from app.db.repositories.rag_cases import RagCaseRepository
from app.db.schema import migrate


def test_rag_case_create_list_delete(tmp_path: Path):
    db = tmp_path / "rag.db"
    migrate(connect(db))
    repo = RagCaseRepository(db)
    c = repo.create(
        title="修真主角",
        type="character",
        description="多角度设定",
        tags=["修真"],
        prompt_en="xianxia hero",
    )
    assert c["id"]
    assert repo.count() == 1
    listed = repo.list(type="character")
    assert len(listed) == 1
    assert listed[0]["tags"] == ["修真"]
    assert repo.delete(c["id"])
    assert repo.count() == 0
