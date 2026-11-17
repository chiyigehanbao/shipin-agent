from unittest.mock import MagicMock

from app.services.comfyui_client import ComfyUIError
from app.services.storyboard_render.worker import StoryboardRenderWorker


def build_worker_fixture(tmp_path):
    casting_reference = tmp_path / "media" / "assets" / "p1" / "suyao.png"
    casting_reference.parent.mkdir(parents=True)
    casting_reference.write_bytes(b"full-casting-image")
    reference = (
        tmp_path / "media" / "assets" / "p1" / "identity" / "suyao-v2.png"
    )
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"purified-reference")
    attempt = {
        "id": "attempt_1",
        "request_id": "request_1",
        "project_id": "p1",
        "frame_id": "f1",
        "asset_id": "asset_output",
        "job_id": "job_1",
        "adapter": "flux_kontext",
        "seed": 42,
        "status": "queued",
    }
    request = {
        "id": "request_1",
        "request": {
            "project_id": "p1",
            "frame_id": "f1",
            "character_identities": [
                {
                    "character_asset_id": "asset_suyao",
                    "character_name": "苏遥",
                    "reference_asset_id": "asset_suyao",
                    "reference_image_url": "/media/assets/p1/identity/suyao-v2.png",
                    "reference_image_hash": "sha256:suyao",
                    "identity_anchor": "balanced oval face and almond eyes",
                    "reference_order": 1,
                    "legacy_reference": False,
                    "reference_source_type": "manual_crop",
                    "reference_version": 2,
                }
            ],
            "look_states": [],
            "weak_characters": [],
            "scene_spec": {"location": "rain alley"},
            "shot_spec": {"shot_type": "medium"},
            "render_policy": {
                "mode": "identity_first",
                "max_strong_identities": 2,
                "allow_temporary_degradation": False,
                "identity_priority": [
                    "face",
                    "age",
                    "hair",
                    "body",
                    "pose",
                    "composition",
                ],
            },
            "compiled_prompt": "Preserve Su Yao's identity.",
            "negative_prompt": "plastic skin",
            "width": 1216,
            "height": 832,
            "source_hash": "source-1",
            "validation": {"valid": True, "issues": []},
        },
    }
    requests = MagicMock()
    requests.get.return_value = request
    attempts = MagicMock()
    attempts.get.return_value = attempt
    assets = MagicMock()
    frames = MagicMock()
    jobs = MagicMock()
    client = MagicMock()
    client.upload_image.return_value = "suyao.png"
    client.submit_workflow.return_value = "prompt_1"
    client.poll_history.return_value = {"filename": "out.png", "type": "output"}
    client.download_image.side_effect = lambda meta, dest: dest.write_bytes(b"candidate")
    adapter = MagicMock()
    adapter.build.return_value = {"4": {"inputs": {"image": "suyao.png"}}}
    identity_evaluator = MagicMock()
    identity_evaluator.evaluate.return_value = {
        "status": "scored",
        "model_fingerprint": "fake-sface-v1",
        "characters": [{"character_asset_id": "asset_suyao", "similarity": 0.61}],
        "warnings": [],
    }
    worker = StoryboardRenderWorker(
        requests=requests,
        attempts=attempts,
        assets=assets,
        frames=frames,
        jobs=jobs,
        client=client,
        adapters={"flux_kontext": adapter},
        output_root=tmp_path / "outputs",
        media_root=tmp_path / "media",
        identity_evaluator=identity_evaluator,
        poll_timeout_sec=5,
        poll_interval_sec=0.01,
    )
    return worker, attempts, client, adapter, reference, identity_evaluator


def test_worker_uploads_reference_and_marks_candidate(tmp_path):
    worker, attempts, client, adapter, reference, identity_evaluator = (
        build_worker_fixture(tmp_path)
    )
    worker.process("attempt_1")
    client.upload_image.assert_called_once_with(reference)
    adapter.build.assert_called_once()
    candidate_calls = [
        call for call in attempts.transition.call_args_list if call.args[1] == "candidate"
    ]
    assert len(candidate_calls) == 1
    assert candidate_calls[0].kwargs["image_url"].endswith("/attempt_1.png")
    identity_evaluator.evaluate.assert_called_once()
    assert attempts.set_identity_evaluation.call_args.args[1]["status"] == "scored"


def test_worker_failure_never_calls_text_adapter(tmp_path):
    worker, attempts, client, _kontext_adapter, _reference, _identity_evaluator = (
        build_worker_fixture(tmp_path)
    )
    text_adapter = MagicMock()
    worker.adapters["text_only_flux"] = text_adapter
    client.submit_workflow.side_effect = ComfyUIError(
        "node_missing: ReferenceLatent"
    )
    worker.process("attempt_1")
    text_adapter.build.assert_not_called()
    failed_calls = [
        call for call in attempts.transition.call_args_list if call.args[1] == "failed"
    ]
    assert len(failed_calls) == 1
    assert "ReferenceLatent" in failed_calls[0].kwargs["error"]["message"]


def test_worker_evaluation_failure_keeps_render_candidate(tmp_path):
    worker, attempts, _client, _adapter, _reference, identity_evaluator = (
        build_worker_fixture(tmp_path)
    )
    identity_evaluator.evaluate.side_effect = RuntimeError("sface failed")

    worker.process("attempt_1")

    assert any(
        call.args[1] == "candidate" for call in attempts.transition.call_args_list
    )
    assert not any(
        call.args[1] == "failed" for call in attempts.transition.call_args_list
    )
    evaluation = attempts.set_identity_evaluation.call_args.args[1]
    assert evaluation["status"] == "unscored"
    assert evaluation["warnings"] == ["identity_evaluation_failed"]
