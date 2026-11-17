from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.services.runtime import storyboard_store

client = TestClient(app)


def test_frame_generate_enqueues_asset():
    frame = storyboard_store.create(
        "p1",
        description="test frame",
        prompt_en="wide shot test",
        negative_prompt="hdr look",
    )
    fid = frame["id"]
    with patch("app.api.storyboard.get_storyboard_render_module") as factory:
        factory.return_value.submit.return_value = {"id": "attempt_1"}
        r = client.post(f"/api/storyboard/p1/frames/{fid}/generate", json={"model": "flux"})
    assert r.status_code == 200
    factory.return_value.submit.assert_called_once()


def test_frame_generate_falls_back_when_prompt_en_empty():
    frame = storyboard_store.create(
        "p1",
        description="咖啡馆门口近景",
        shot_type="近景",
        scene="咖啡馆",
        prompt_en="",
    )
    fid = frame["id"]
    with patch("app.api.storyboard.get_storyboard_render_module") as factory:
        factory.return_value.submit.return_value = {"id": "attempt_2"}
        r = client.post(f"/api/storyboard/p1/frames/{fid}/generate", json={"model": "flux"})
    assert r.status_code == 200
    factory.return_value.submit.assert_called_once()


def test_frame_generate_rejects_unready_character():
    frame = storyboard_store.create(
        "p_gate",
        description="苏遥近景",
        prompt_en="A clear close-up of Su Yao under moonlight, 85mm",
        character="苏遥",
    )
    fid = frame["id"]
    from app.services.storyboard_render.types import StoryboardRenderError

    with patch("app.api.storyboard.get_storyboard_render_module") as factory:
        factory.return_value.submit.side_effect = StoryboardRenderError(
            "casting_reference_missing", "角色苏遥缺少定妆参考图"
        )
        r = client.post(
            f"/api/storyboard/p_gate/frames/{fid}/generate",
            json={"model": "flux"},
        )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "casting_reference_missing"
