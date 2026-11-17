from app.services.tts.edge_provider import EdgeTTSProvider


def test_edge_synthesize_returns_bytes(monkeypatch):
    async def fake_save(text, path, voice):
        from pathlib import Path

        Path(path).write_bytes(b"RIFF_FAKE_WAV")

    monkeypatch.setattr(
        "app.services.tts.edge_provider._edge_save",
        fake_save,
    )
    audio = EdgeTTSProvider(voice="zh-CN-XiaoxiaoNeural").synthesize(
        text="测试", emotion="平静"
    )
    assert audio.startswith(b"RIFF")
