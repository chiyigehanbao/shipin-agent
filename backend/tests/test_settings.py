from pathlib import Path

from app.core.settings import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.comfyui_base_url == "http://127.0.0.1:8000"
    assert s.poll_timeout_sec == 600.0
    assert s.poll_interval_sec == 1.5


def test_env_override(monkeypatch):
    monkeypatch.setenv("MODELHUB_ROOT", r"D:\ModelHub")
    monkeypatch.setenv("COMFYUI_BASE_URL", "http://127.0.0.1:9999")
    s = Settings(_env_file=None)
    assert s.modelhub_root == Path(r"D:\ModelHub")
    assert s.comfyui_base_url == "http://127.0.0.1:9999"
    assert s.assets_output_dir == Path(r"D:\ModelHub\outputs\assets")
    assert s.media_mount_dir == Path(r"D:\ModelHub\outputs")


def test_comfyui_models_dir_under_modelhub(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELHUB_ROOT", str(tmp_path))
    s = Settings(_env_file=None)
    assert s.comfyui_models_dir == Path(tmp_path) / "comfyui" / "models"
