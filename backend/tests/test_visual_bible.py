from app.db.repositories.visual_specs import VisualSpecRepository
from app.services.visual_bible import default_visual_bible


def test_default_visual_bible_is_polished_without_permanent_distress():
    bible = default_visual_bible()
    text = bible.model_dump_json().lower()
    assert "commercial short-drama" in text
    for forbidden in ("grit", "cold sweat", "exhausted", "mud-stained"):
        assert forbidden not in text


def test_visual_spec_roundtrip(tmp_path):
    db = tmp_path / "spec.db"
    repo = VisualSpecRepository(db)
    saved = repo.upsert("p1", default_visual_bible().model_dump())
    loaded = repo.get("p1")
    assert loaded is not None
    assert loaded["spec_json"]["version"] == saved["spec_json"]["version"]
    assert loaded["project_id"] == "p1"
