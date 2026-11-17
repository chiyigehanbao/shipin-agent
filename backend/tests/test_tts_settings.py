from pathlib import Path

from app.services.tts_settings_store import TtsSettingsStore


def test_tts_settings_roundtrip(tmp_path: Path):
    store = TtsSettingsStore(tmp_path / "tts.json")
    assert store.get()["engine"] == "edge"
    saved = store.save({"engine": "voxcpm", "edge_voice": "zh-CN-YunxiNeural"})
    assert saved["engine"] == "voxcpm"
    assert store.get()["edge_voice"] == "zh-CN-YunxiNeural"
