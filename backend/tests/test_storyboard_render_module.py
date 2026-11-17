import hashlib
from unittest.mock import MagicMock

import pytest

from app.db.repositories.assets import AssetRepository
from app.db.repositories.frames import FrameRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.scenes import SceneRepository
from app.db.repositories.storyboard_renders import (
    RenderAttemptRepository,
    RenderRequestRepository,
)
from app.services.storyboard_render.adapters import AdapterReadiness
from app.services.storyboard_render.module import StoryboardRenderModule
from app.services.storyboard_render.types import RenderPolicy, StoryboardRenderError
from app.services.visual_bible import VisualBibleService


def build_module_fixture(tmp_path):
    db = tmp_path / "module.db"
    media_root = tmp_path / "media"
    reference_path = media_root / "assets" / "p1" / "suyao.png"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(b"stable-reference")
    purified_path = media_root / "assets" / "p1" / "identity" / "suyao-v2.png"
    purified_path.parent.mkdir(parents=True)
    purified_path.write_bytes(b"purified-reference")
    assets = AssetRepository(db)
    character = assets.create(
        project_id="p1",
        name="苏遥",
        type="character",
        prompt_cn="",
        prompt_en="portrait",
        model="flux",
        status="completed",
        lock_en="balanced oval face and almond eyes",
        selection_status="selected",
        identity={
            "identity_anchor": "balanced oval face and almond eyes",
            "reference": {
                "status": "ready",
                "source_type": "manual_crop",
                "image_url": "/media/assets/p1/identity/suyao-v2.png",
                "image_hash": "sha256:stored-value",
                "version": 2,
            },
        },
    )
    character = assets.update(
        "p1", character["id"], image_url="/media/assets/p1/suyao.png"
    )
    scenes = SceneRepository(db)
    scene = scenes.replace_all("p1", [{"name": "雨巷", "location": "rain alley"}])[0]
    frames = FrameRepository(db)
    frame = frames.create(
        "p1",
        scene_id=scene["id"],
        scene=scene["name"],
        character="苏遥",
        description_en="Su Yao crosses the alley",
    )
    requests = RenderRequestRepository(db)
    attempts = RenderAttemptRepository(db)
    jobs = JobRepository(db)
    adapter = MagicMock()
    adapter.name = "flux_kontext"
    adapter.workflow_version = "kontext-gguf-v1"
    adapter.model_fingerprint = "unet/flux1-kontext-dev-Q4_K_S.gguf"
    adapter.preflight.return_value = AdapterReadiness(ready=True)
    client = MagicMock()
    client.health.return_value = True
    client.available_node_types.return_value = {"ReferenceLatent"}
    enqueue = MagicMock()
    module = StoryboardRenderModule(
        frames=frames,
        scenes=scenes,
        assets=assets,
        requests=requests,
        attempts=attempts,
        jobs=jobs,
        visual_bible=VisualBibleService(db_path=db),
        client=client,
        adapters={"flux_kontext": adapter},
        enqueue=enqueue,
        media_root=media_root,
        models_dir=tmp_path / "models",
    )
    return module, frame, requests, attempts, frames, enqueue


def test_module_submits_traceable_attempt_and_detects_stale_state(tmp_path):
    module, frame, requests, attempts, frames, enqueue = build_module_fixture(tmp_path)
    attempt = module.submit("p1", frame["id"], policy=RenderPolicy(), seed=42)
    assert attempt["adapter"] == "flux_kontext"
    assert attempt["model_fingerprint"].endswith("Q4_K_S.gguf")
    assert requests.get(attempt["request_id"])["request"]["source_hash"]
    compiled_identity = requests.get(attempt["request_id"])["request"][
        "character_identities"
    ][0]
    assert compiled_identity["reference_image_url"].endswith("/identity/suyao-v2.png")
    expected_hash = hashlib.sha256(b"purified-reference").hexdigest()
    assert compiled_identity["reference_image_hash"] == f"sha256:{expected_hash}"
    enqueue.assert_called_once_with(attempt["id"])
    assert module.get_state("p1", frame["id"])["stale"] is False
    frames.update("p1", frame["id"], description_en="A different action")
    assert module.get_state("p1", frame["id"])["stale"] is True


def test_module_accepts_candidate_and_rejects_unknown_reason(tmp_path):
    module, frame, _requests, attempts, frames, _enqueue = build_module_fixture(tmp_path)
    attempt = module.submit("p1", frame["id"], policy=RenderPolicy(), seed=7)
    attempts.transition(attempt["id"], "running")
    attempts.transition(
        attempt["id"],
        "candidate",
        image_url=f"/media/assets/p1/{attempt['id']}.png",
    )
    accepted = module.accept("p1", frame["id"], attempt["id"])
    assert accepted["status"] == "accepted"
    updated = frames.get("p1", frame["id"])
    assert updated["accepted_render_attempt_id"] == attempt["id"]
    assert updated["image_url"].endswith(f"/{attempt['id']}.png")
    with pytest.raises(StoryboardRenderError, match="invalid_rejection_reason"):
        module.reject("p1", frame["id"], attempt["id"], "bad", "")
