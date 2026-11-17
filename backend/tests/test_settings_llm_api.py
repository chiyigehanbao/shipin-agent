from unittest.mock import patch

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm_provider import LLMError
from app.services.llm_settings_store import LlmSettingsStore

client = TestClient(app)


def test_get_llm_defaults(tmp_path, monkeypatch):
    path = tmp_path / "llm_settings.json"
    monkeypatch.setattr("app.services.llm_runtime.STORE_PATH", path)
    r = client.get("/api/settings/llm")
    assert r.status_code == 200
    body = r.json()
    assert "ollama_model" in body
    assert body["api_key_set"] is False
    assert "cloud_llm_api_key" not in body or body.get("cloud_llm_api_key") is None
    assert "cloud_profiles" in body


def test_put_llm_overrides_model(tmp_path, monkeypatch):
    path = tmp_path / "llm_settings.json"
    monkeypatch.setattr("app.services.llm_runtime.STORE_PATH", path)
    r = client.put(
        "/api/settings/llm",
        json={"ollama_model": "qwen3.5:9b", "llm_timeout_sec": 30.0},
    )
    assert r.status_code == 200
    assert r.json()["ollama_model"] == "qwen3.5:9b"
    assert LlmSettingsStore(path)._read_file()["ollama_model"] == "qwen3.5:9b"


def test_put_profiles(tmp_path, monkeypatch):
    path = tmp_path / "llm_settings.json"
    monkeypatch.setattr("app.services.llm_runtime.STORE_PATH", path)
    r = client.put(
        "/api/settings/llm",
        json={
            "active_cloud_id": "deepseek",
            "cloud_profiles": [
                {
                    "id": "deepseek",
                    "name": "DeepSeek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-secret",
                    "model": "deepseek-chat",
                },
                {
                    "id": "openai",
                    "name": "OpenAI",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-oa",
                    "model": "gpt-4o-mini",
                },
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["cloud_profiles"]) == 2
    assert "sk-secret" not in str(body)


def test_paths_endpoint():
    r = client.get("/api/settings/paths")
    assert r.status_code == 200
    assert "modelhub_root" in r.json()
    assert "sqlite_path" in r.json()


@respx.mock
def test_ollama_models(tmp_path, monkeypatch):
    path = tmp_path / "llm_settings.json"
    monkeypatch.setattr("app.services.llm_runtime.STORE_PATH", path)
    respx.get("http://127.0.0.1:11434/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3"}]}
        )
    )
    r = client.get("/api/settings/llm/ollama/models")
    assert r.status_code == 200
    names = [m["name"] for m in r.json()["models"]]
    assert "qwen2.5:7b" in names


def test_llm_test_endpoint_ok(tmp_path, monkeypatch):
    path = tmp_path / "llm_settings.json"
    monkeypatch.setattr("app.services.llm_runtime.STORE_PATH", path)

    class FakeProvider:
        def chat(self, messages):
            return "OK", "ollama"

    with patch("app.api.settings_llm.build_llm_provider", return_value=FakeProvider()):
        r = client.post("/api/settings/llm/test")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["provider"] == "ollama"


def test_llm_test_endpoint_502(tmp_path, monkeypatch):
    path = tmp_path / "llm_settings.json"
    monkeypatch.setattr("app.services.llm_runtime.STORE_PATH", path)

    class FakeProvider:
        def chat(self, messages):
            raise LLMError("本地与云端 LLM 均不可用")

    with patch("app.api.settings_llm.build_llm_provider", return_value=FakeProvider()):
        r = client.post("/api/settings/llm/test")
    assert r.status_code == 502
