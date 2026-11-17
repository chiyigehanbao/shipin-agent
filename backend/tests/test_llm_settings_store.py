from pathlib import Path

from app.services.llm_settings_store import LlmSettingsStore


def test_load_defaults_when_missing(tmp_path: Path):
    store = LlmSettingsStore(tmp_path / "llm_settings.json")
    cfg = store.get_effective(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:7b",
        cloud_llm_base_url="",
        cloud_llm_api_key="",
        cloud_llm_model="gpt-4o-mini",
        llm_timeout_sec=60.0,
    )
    assert cfg["ollama_model"] == "qwen2.5:7b"
    assert cfg["api_key_set"] is False


def test_save_overrides_and_masks_key(tmp_path: Path):
    path = tmp_path / "llm_settings.json"
    store = LlmSettingsStore(path)
    store.save(
        {
            "ollama_base_url": "http://ollama:11434",
            "ollama_model": "qwen3.5:9b",
            "cloud_llm_base_url": "https://api.openai.com/v1",
            "cloud_llm_api_key": "sk-secret",
            "cloud_llm_model": "gpt-4o-mini",
            "llm_timeout_sec": 30.0,
        }
    )
    public = store.get_public(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:7b",
        cloud_llm_base_url="",
        cloud_llm_api_key="",
        cloud_llm_model="gpt-4o-mini",
        llm_timeout_sec=60.0,
    )
    assert public["ollama_model"] == "qwen3.5:9b"
    assert public["api_key_set"] is True
    assert "sk-secret" not in str(public)


def test_migrate_legacy_flat(tmp_path: Path):
    path = tmp_path / "llm_settings.json"
    path.write_text(
        '{"cloud_llm_base_url":"https://x","cloud_llm_api_key":"sk-ab","cloud_llm_model":"m"}',
        encoding="utf-8",
    )
    store = LlmSettingsStore(path)
    pub = store.get_public(
        ollama_base_url="http://o",
        ollama_model="q",
        cloud_llm_base_url="",
        cloud_llm_api_key="",
        cloud_llm_model="",
        llm_timeout_sec=60,
    )
    assert pub["active_cloud_id"] == "legacy"
    assert pub["cloud_profiles"][0]["api_key_set"] is True
    assert "sk-ab" not in str(pub)


def test_active_profile_in_effective(tmp_path: Path):
    store = LlmSettingsStore(tmp_path / "s.json")
    store.save(
        {
            "active_cloud_id": "deepseek",
            "cloud_profiles": [
                {
                    "id": "deepseek",
                    "name": "DeepSeek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-ds",
                    "model": "deepseek-chat",
                }
            ],
        }
    )
    eff = store.get_effective(
        ollama_base_url="http://o",
        ollama_model="q",
        cloud_llm_base_url="",
        cloud_llm_api_key="",
        cloud_llm_model="",
        llm_timeout_sec=60,
    )
    assert eff["cloud_llm_base_url"].startswith("https://api.deepseek")
    assert eff["cloud_llm_api_key"] == "sk-ds"
