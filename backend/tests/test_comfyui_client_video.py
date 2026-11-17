from unittest.mock import MagicMock

from app.services.comfyui_client import ComfyUIClient


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_poll_history_returns_video_meta():
    c = ComfyUIClient("http://127.0.0.1:9")
    hist = {
        "pid": {
            "status": {"completed": True, "status_str": "success"},
            "outputs": {
                "12": {
                    "videos": [
                        {
                            "filename": "out.mp4",
                            "subfolder": "vf",
                            "type": "output",
                        }
                    ]
                }
            },
        }
    }
    c._client = MagicMock()
    c._client.get.return_value = _FakeResp(hist)
    meta = c.poll_history("pid", timeout_sec=1, media_kinds=("videos", "images"))
    assert meta["filename"] == "out.mp4"
    assert meta["_media_kind"] == "videos"
