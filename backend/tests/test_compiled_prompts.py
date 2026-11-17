from app.db.repositories.compiled_prompts import CompiledPromptRepository


def test_compiled_prompt_roundtrip_and_latest(tmp_path):
    db = tmp_path / "compiled.db"
    repo = CompiledPromptRepository(db)
    row = repo.create(
        project_id="p1",
        source_type="frame",
        source_id="f1",
        target_model="minimax-h3",
        mode="i2va",
        source_hash="abc",
        guide_version="g1",
        content="body",
        validation={"valid": True, "issues": []},
        provider="ollama",
    )
    latest = repo.latest("p1", "frame", "f1", "i2va")
    assert latest is not None
    assert latest["id"] == row["id"]
    assert latest["validation_json"]["valid"] is True


def test_compiled_prompt_update_preserves_unset_fields(tmp_path):
    db = tmp_path / "compiled.db"
    repo = CompiledPromptRepository(db)
    row = repo.create(
        project_id="p1",
        source_type="frame",
        source_id="f1",
        target_model="minimax-h3",
        mode="i2va",
        source_hash="abc",
        guide_version="g1",
        content="first",
        validation={"valid": True, "issues": []},
        provider="ollama",
    )
    updated = repo.update(row["id"], content="edited", status="locked", is_user_edited=True)
    assert updated["content"] == "edited"
    assert updated["status"] == "locked"
    assert updated["guide_version"] == "g1"
    assert updated["is_user_edited"] is True
