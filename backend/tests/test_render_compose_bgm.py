from pathlib import Path
from unittest.mock import MagicMock

from app.db.repositories.frames import FrameRepository
from app.db.repositories.renders import RenderRepository
from app.services.render_compose import RenderComposeService


class FakeAceStep:
    def __init__(self, available=True):
        self.available = available
        self.called = False

    def is_available(self):
        return self.available

    def generate_bgm(self, **kw):
        self.called = True
        out = Path(kw["out_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fakebgm")
        return str(out)


def _make_svc(tmp_path: Path):
    db = tmp_path / "r.db"
    media = tmp_path / "media"
    media.mkdir()
    frames = FrameRepository(db_path=db)
    img = media / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    frames.create(
        "p1",
        scene_id="s1",
        image_url="/media/a.png",
        duration=1,
        lines=[
            {
                "id": "l1",
                "type": "narration",
                "speaker": "旁白",
                "text": "一",
                "emotion": "",
            }
        ],
    )
    tts = MagicMock()
    tts.synthesize.return_value = b"RIFF_FAKE"
    return RenderComposeService(
        frame_repo=frames,
        render_repo=RenderRepository(db_path=db),
        tts=tts,
        media_root=media,
        media_url_prefix="/media",
    )


def _fake_ffmpeg(cmd):
    out = Path(cmd[-1])
    out.write_bytes(b"ftypisom")
    return 0


def test_compose_generates_bgm_when_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.render_compose.run_ffmpeg", _fake_ffmpeg)
    svc = _make_svc(tmp_path)
    ace = FakeAceStep(available=True)
    result = svc.compose(
        project_id="p1",
        bgm_enabled=True,
        bgm_caption="cinematic ambient, soft pads, instrumental",
        ace_step=ace,
    )
    assert result["output_url"].startswith("/media/")
    assert ace.called is True
    assert not any("BGM" in w and ("失败" in w or "未启动" in w) for w in result["warnings"])


def test_compose_skips_bgm_when_unavailable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.render_compose.run_ffmpeg", _fake_ffmpeg)
    svc = _make_svc(tmp_path)
    ace = FakeAceStep(available=False)
    result = svc.compose(project_id="p1", bgm_enabled=True, ace_step=ace)
    assert any("BGM" in w and "不可用" in w for w in result["warnings"])
    assert ace.called is False


def test_compose_bgm_off_does_not_call_ace(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.render_compose.run_ffmpeg", _fake_ffmpeg)
    svc = _make_svc(tmp_path)
    ace = FakeAceStep(available=True)
    result = svc.compose(project_id="p1", bgm_enabled=False, ace_step=ace)
    assert result["output_url"].startswith("/media/")
    assert ace.called is False
