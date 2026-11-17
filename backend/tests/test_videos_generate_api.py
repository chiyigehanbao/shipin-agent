from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.db.repositories.compiled_prompts import CompiledPromptRepository

client = TestClient(app)

COMPILED_T2VA = """integrated_multimodal_description: [Shot 1] Live-action, cinematic, a rain-soaked dock at night.

overall_soundscape: Rain falls on timber while distant water moves.

non_diegetic_music: N/A"""


def test_video_generate_requires_prompt():
    r = client.post("/api/videos/p1/generate", json={"prompt_en": "  "})
    assert r.status_code == 422 or r.status_code == 400


def test_video_generate_queues_when_ready():
    with patch(
        "app.api.videos.check_model",
        return_value={"ready": True, "missing_files": []},
    ):
        with patch("app.api.videos.client.health", return_value=True):
            with patch("app.api.videos.get_h3_compiler") as compiler_factory:
                compiler_factory.return_value.compile_t2va.return_value = {
                    "id": "cp_t2va",
                    "content": COMPILED_T2VA,
                    "validation_json": {"valid": True, "issues": []},
                    "guide_version": "minimax-h3@d21241f",
                    "stale": False,
                }
                with patch("app.api.videos.job_queue.enqueue") as enq:
                    with patch("app.api.videos.job_repo.create") as create:
                        create.return_value = {
                            "id": "job_v1",
                            "type": "video_generate",
                            "status": "queued",
                        }
                        r = client.post(
                            "/api/videos/p1/generate",
                            json={"prompt_en": "rainy dock night cinematic"},
                        )
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == "job_v1"
    assert body["model"] == "minimax"
    assert body["mode"] == "t2v"
    enq.assert_called_once_with("job_v1")
    payload = create.call_args.kwargs["payload"]
    assert payload["prompt_en"] == COMPILED_T2VA
    assert payload["compiled_prompt_id"] == "cp_t2va"


def test_video_generate_503_when_comfy_down():
    with patch(
        "app.api.videos.check_model",
        return_value={"ready": True, "missing_files": []},
    ):
        with patch("app.api.videos.client.health", return_value=False):
            r = client.post(
                "/api/videos/p1/generate",
                json={"prompt_en": "a cat walks"},
            )
    assert r.status_code == 503
    assert r.json()["detail"] == "comfyui_unavailable"


def test_video_generate_rejects_compiled_prompt_for_changed_brief():
    artifact = CompiledPromptRepository().create(
        project_id="p_stale",
        source_type="project",
        source_id="project",
        target_model="minimax-h3",
        mode="t2va",
        source_hash="old-source-hash",
        guide_version="minimax-h3@d21241f",
        content=COMPILED_T2VA,
        validation={"valid": True, "issues": []},
        provider="ollama",
    )
    with patch("app.api.videos.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.videos.client.health", return_value=True):
            with patch("app.api.videos.job_queue.enqueue") as enqueue:
                response = client.post(
                    "/api/videos/p_stale/generate",
                    json={
                        "prompt_en": "a completely changed creative brief",
                        "compiled_prompt_id": artifact["id"],
                    },
                )
    assert response.status_code == 409
    enqueue.assert_not_called()
