from unittest.mock import MagicMock

import httpx

from app.services.llm_provider import LLMError, LLMProvider


def test_ollama_success_returns_provider_ollama():
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "message": {"content": '{"prompt_en":"a","avoid":"b","interpretation_cn":"c","prompt_cn":""}'}
    }
    resp.raise_for_status = MagicMock()
    client.post.return_value = resp
    p = LLMProvider(
        ollama_base_url="http://ollama",
        ollama_model="qwen",
        cloud_llm_base_url="http://cloud/v1",
        cloud_llm_api_key="k",
        cloud_llm_model="m",
        timeout_sec=5,
        client=client,
    )
    text, provider = p.chat([{"role": "user", "content": "hi"}])
    assert provider == "ollama"
    assert "prompt_en" in text
    assert client.post.call_args.args[0].startswith("http://ollama/")


def test_ollama_fail_falls_back_to_cloud():
    client = MagicMock()

    def post(url, **kwargs):
        if "ollama" in url:
            raise httpx.ConnectError("down", request=MagicMock())
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": "cloud-ok"}}]
        }
        resp.raise_for_status = MagicMock()
        return resp

    client.post.side_effect = post
    p = LLMProvider(
        ollama_base_url="http://ollama",
        ollama_model="qwen",
        cloud_llm_base_url="http://cloud/v1",
        cloud_llm_api_key="k",
        cloud_llm_model="m",
        timeout_sec=5,
        client=client,
    )
    text, provider = p.chat([{"role": "user", "content": "hi"}])
    assert provider == "cloud"
    assert text == "cloud-ok"


def test_both_fail_raises():
    client = MagicMock()
    client.post.side_effect = httpx.ConnectError("down", request=MagicMock())
    p = LLMProvider(
        ollama_base_url="http://ollama",
        ollama_model="qwen",
        cloud_llm_base_url="http://cloud/v1",
        cloud_llm_api_key="k",
        cloud_llm_model="m",
        timeout_sec=5,
        client=client,
    )
    try:
        p.chat([{"role": "user", "content": "hi"}])
        assert False, "expected LLMError"
    except LLMError as e:
        assert "均不可用" in str(e) or "unavailable" in str(e).lower()
