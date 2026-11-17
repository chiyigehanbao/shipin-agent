from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from app.services.asset_store import AssetStore
from app.services.identity_reference.face_backend import UnavailableFaceBackend
from app.services.identity_reference.generation import IdentityReferenceGenerator
from app.services.identity_reference.service import IdentityReferenceService
from app.services.job_handlers import dispatch_job


def _build_fixture(tmp_path: Path, *, confirmed: bool):
    media_root = tmp_path / "media"
    output_root = media_root / "assets"
    casting = media_root / "assets" / "p1" / "casting.png"
    casting.parent.mkdir(parents=True)
    Image.new("RGB", (900, 1200), "#806f68").save(casting)
    reference = media_root / "assets" / "p1" / "identity" / "v1.png"
    reference.parent.mkdir(parents=True)
    Image.new("RGB", (768, 768), "#8a7469").save(reference)
    identity = {"identity_anchor": "balanced oval face and almond eyes"}
    if confirmed:
        identity["reference"] = {
            "status": "ready",
            "image_url": "/media/assets/p1/identity/v1.png",
            "image_hash": "sha256:old",
            "source_type": "manual_crop",
            "version": 1,
        }
    store = AssetStore(tmp_path / "generation.db")
    asset = store.create(
        project_id="p1",
        name="苏遥",
        type="character",
        prompt_cn="",
        prompt_en="portrait",
        model="flux",
        status="completed",
        selection_status="selected",
        identity=identity,
    )
    asset = store.update(
        "p1", asset["id"], image_url="/media/assets/p1/casting.png"
    )
    references = IdentityReferenceService(
        assets=store,
        face_backend=UnavailableFaceBackend("face_model_files_missing"),
        media_root=media_root,
        output_root=output_root,
    )
    client = MagicMock()
    client.upload_image.return_value = "identity-input.png"
    client.submit_workflow.return_value = "prompt-1"
    client.poll_history.return_value = {"filename": "generated.png", "type": "output"}

    def download(_meta, path):
        Image.new("RGB", (768, 768), "#90796e").save(path)
        return path

    client.download_image.side_effect = download
    adapter = MagicMock()
    adapter.build.return_value = {"workflow": "identity"}
    generator = IdentityReferenceGenerator(
        assets=store,
        identity_references=references,
        client=client,
        adapter=adapter,
        media_root=media_root,
        output_root=output_root,
        poll_timeout_sec=5,
        poll_interval_sec=0.01,
    )
    return generator, store, asset, client, adapter, casting, reference


def test_generation_uses_confirmed_reference_and_keeps_it_pending(tmp_path: Path):
    generator, store, asset, client, adapter, _casting, reference = _build_fixture(
        tmp_path, confirmed=True
    )
    previous_reference = dict(asset["identity"]["reference"])

    result = generator.run(project_id="p1", asset_id=asset["id"], seed=42)

    candidate = result["candidate"]
    updated = store.get("p1", asset["id"])
    assert candidate["source_type"] == "generated"
    assert candidate["status"] == "pending"
    assert updated["identity"]["reference"] == previous_reference
    client.upload_image.assert_called_once_with(reference)
    request = adapter.build.call_args.kwargs["request"]
    assert "neutral expression" in request.compiled_prompt.lower()
    assert "plain neutral background" in request.compiled_prompt.lower()
    assert request.width == request.height == 768


def test_generation_falls_back_to_full_casting_image(tmp_path: Path):
    generator, _store, asset, client, _adapter, casting, _reference = _build_fixture(
        tmp_path, confirmed=False
    )

    generator.run(project_id="p1", asset_id=asset["id"], seed=7)

    client.upload_image.assert_called_once_with(casting)


def test_generation_job_handler_delegates_without_storyboard_state():
    job = {
        "id": "job_identity",
        "type": "identity_reference_generate",
        "project_id": "p1",
        "payload": {"asset_id": "a1", "seed": 42},
    }
    with patch("app.services.runtime.identity_reference_generator") as generator, patch(
        "app.services.runtime.job_repo"
    ) as job_repo:
        generator.run.return_value = {"candidate": {"id": "identity_1"}}
        result = dispatch_job(job)

    generator.run.assert_called_once_with(project_id="p1", asset_id="a1", seed=42)
    job_repo.update.assert_called_once_with("job_identity", progress=20)
    assert result["candidate"]["id"] == "identity_1"
