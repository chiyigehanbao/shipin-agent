from __future__ import annotations

import httpx
import pytest
import respx
from app.services.comfyui_client import ComfyUIClient, ComfyUIError


@pytest.fixture
def client():
    return ComfyUIClient(base_url="http://127.0.0.1:8188", timeout=5.0)


@respx.mock
def test_health_ok(client):
    respx.get("http://127.0.0.1:8188/system_stats").mock(
        return_value=httpx.Response(200, json={"system": {}})
    )
    assert client.health() is True


@respx.mock
def test_health_down(client):
    c = ComfyUIClient(
        base_url="http://127.0.0.1:8188",
        timeout=5.0,
        probe_urls=["http://127.0.0.1:8188"],
    )
    respx.get("http://127.0.0.1:8188/system_stats").mock(
        side_effect=httpx.ConnectError("down")
    )
    assert c.health() is False


@respx.mock
def test_health_auto_switches_to_alternate_port():
    c = ComfyUIClient(
        base_url="http://127.0.0.1:8188",
        timeout=5.0,
        probe_urls=["http://127.0.0.1:8188", "http://127.0.0.1:8000"],
        probe_timeout=2.0,
    )
    respx.get("http://127.0.0.1:8188/system_stats").mock(
        return_value=httpx.Response(503)
    )
    respx.get("http://127.0.0.1:8000/system_stats").mock(
        return_value=httpx.Response(200, json={"system": {"comfyui_version": "0.31.0"}})
    )
    assert c.health() is True
    assert c.base_url == "http://127.0.0.1:8000"


def test_default_probe_covers_8000_range():
    from app.services.comfyui_client import DEFAULT_PROBE_URLS

    assert "http://127.0.0.1:8000" in DEFAULT_PROBE_URLS
    assert "http://127.0.0.1:8010" in DEFAULT_PROBE_URLS
    assert "http://127.0.0.1:8188" in DEFAULT_PROBE_URLS
    assert len(DEFAULT_PROBE_URLS) >= 20


@respx.mock
def test_submit_returns_prompt_id(client):
    respx.post("http://127.0.0.1:8188/prompt").mock(
        return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
    )
    assert client.submit_workflow({"1": {}}) == "abc-123"


@respx.mock
def test_prompt_stays_bound_to_server_used_for_submission(tmp_path, client):
    respx.post("http://127.0.0.1:8188/prompt").mock(
        return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
    )
    respx.get("http://127.0.0.1:8188/history/abc-123").mock(
        return_value=httpx.Response(
            200,
            json={
                "abc-123": {
                    "outputs": {
                        "9": {
                            "images": [
                                {
                                    "filename": "x.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    }
                }
            },
        )
    )
    respx.get("http://127.0.0.1:8188/view").mock(
        return_value=httpx.Response(200, content=b"PNGDATA")
    )

    prompt_id = client.submit_workflow({"1": {}})
    client.set_base_url("http://127.0.0.1:8001", persist=False)
    meta = client.poll_history(prompt_id, timeout_sec=1, interval_sec=0.01)
    dest = tmp_path / "out.png"
    client.download_image(meta, dest)

    assert meta["_comfy_base_url"] == "http://127.0.0.1:8188"
    assert dest.read_bytes() == b"PNGDATA"


@respx.mock
def test_available_node_types(client):
    respx.get("http://127.0.0.1:8188/object_info").mock(
        return_value=httpx.Response(
            200,
            json={"LoadImage": {"input": {}}, "ReferenceLatent": {"input": {}}},
        )
    )
    assert client.available_node_types() == {"LoadImage", "ReferenceLatent"}


@respx.mock
def test_available_node_types_rejects_invalid_payload(client):
    respx.get("http://127.0.0.1:8188/object_info").mock(
        return_value=httpx.Response(200, json=["LoadImage"])
    )
    with pytest.raises(ComfyUIError, match="invalid object_info"):
        client.available_node_types()


@respx.mock
def test_poll_history_completed(client):
    respx.get("http://127.0.0.1:8188/history/abc-123").mock(
        return_value=httpx.Response(
            200,
            json={
                "abc-123": {
                    "outputs": {
                        "9": {
                            "images": [
                                {
                                    "filename": "x.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    }
                }
            },
        )
    )
    meta = client.poll_history("abc-123", timeout_sec=1, interval_sec=0.01)
    assert meta["filename"] == "x.png"


@respx.mock
def test_poll_history_surfaces_cuda_error(client):
    respx.get("http://127.0.0.1:8188/history/abc-123").mock(
        return_value=httpx.Response(
            200,
            json={
                "abc-123": {
                    "outputs": {},
                    "status": {
                        "status_str": "error",
                        "completed": False,
                        "messages": [
                            [
                                "execution_error",
                                {
                                    "node_type": "CLIPTextEncode",
                                    "exception_type": "RuntimeError",
                                    "exception_message": (
                                        "CUDA error: no kernel image is available "
                                        "for execution on the device\nmore"
                                    ),
                                },
                            ]
                        ],
                    },
                }
            },
        )
    )
    with pytest.raises(Exception) as ei:
        client.poll_history("abc-123", timeout_sec=1, interval_sec=0.01)
    assert "CUDA error" in str(ei.value)
    assert "CLIPTextEncode" in str(ei.value)


@respx.mock
def test_download_image(tmp_path, client):
    respx.get("http://127.0.0.1:8188/view").mock(
        return_value=httpx.Response(200, content=b"PNGDATA")
    )
    dest = tmp_path / "out.png"
    client.download_image(
        {"filename": "x.png", "subfolder": "", "type": "output"}, dest
    )
    assert dest.read_bytes() == b"PNGDATA"


@respx.mock
def test_submit_surfaces_comfy_node_errors(client):
    respx.post("http://127.0.0.1:8188/prompt").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "type": "prompt_outputs_failed_validation",
                    "message": "Prompt outputs failed validation",
                },
                "node_errors": {
                    "13": {
                        "class_type": "DualCLIPLoader",
                        "errors": [
                            {
                                "type": "value_not_in_list",
                                "details": (
                                    "clip_name2: 't5-v1_1-xxl-encoder-Q4_K_S.gguf' "
                                    "not in []"
                                ),
                            }
                        ],
                    }
                },
            },
        )
    )
    with pytest.raises(Exception) as ei:
        client.submit_workflow({"1": {}})
    msg = str(ei.value)
    assert "400" in msg
    assert "DualCLIPLoader" in msg
    assert "clip_name2" in msg
