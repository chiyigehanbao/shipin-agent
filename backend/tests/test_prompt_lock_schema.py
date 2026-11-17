from app.db.repositories.assets import AssetRepository
from app.db.repositories.frames import FrameRepository


def test_asset_lock_en_roundtrip(tmp_path):
    repo = AssetRepository(tmp_path / "a.db")
    item = repo.create(
        project_id="p",
        name="张三",
        type="character",
        prompt_cn="x",
        prompt_en="y",
        model="flux",
        lock_en="LOCK",
        status="pending",
    )
    assert item["lock_en"] == "LOCK"
    updated = repo.update("p", item["id"], lock_en="LOCK2")
    assert updated["lock_en"] == "LOCK2"


def test_asset_identity_roundtrip(tmp_path):
    repo = AssetRepository(tmp_path / "identity.db")
    identity = {
        "identity_anchor": "soft oval face, clear almond eyes",
        "stable_traits": ["facial_geometry", "stable_hairstyle"],
        "source": "casting_v1",
    }
    item = repo.create(
        project_id="p",
        name="A",
        type="character",
        prompt_cn="",
        prompt_en="portrait",
        model="flux",
        identity=identity,
    )
    assert item["identity"] == identity
    updated = repo.update(
        "p", item["id"], identity={**identity, "source": "manual"}
    )
    assert updated["identity"]["source"] == "manual"


def test_frame_motion_prompt_roundtrip(tmp_path):
    repo = FrameRepository(tmp_path / "f.db")
    fr = repo.create(
        project_id="p", description="d", prompt_en="still", motion_prompt_en="move"
    )
    assert fr["motion_prompt_en"] == "move"
    updated = repo.update("p", fr["id"], motion_prompt_en="move2")
    assert updated["motion_prompt_en"] == "move2"
