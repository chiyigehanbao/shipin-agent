from pathlib import Path
from unittest.mock import MagicMock

from app.db.repositories.frames import FrameRepository
from app.db.repositories.renders import RenderRepository
from app.services.render_compose import RenderComposeService


def test_compose_builds_output(tmp_path: Path, monkeypatch):
    db = tmp_path / "r.db"
    media = tmp_path / "media"
    media.mkdir()
    frames = FrameRepository(db_path=db)
    img1 = media / "a.png"
    img2 = media / "b.png"
    img1.write_bytes(b"\x89PNG\r\n\x1a\n")
    img2.write_bytes(b"\x89PNG\r\n\x1a\n")
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
    frames.create(
        "p1",
        scene_id="s1",
        image_url="/media/b.png",
        duration=1,
        lines=[],
    )
    tts = MagicMock()
    tts.synthesize.return_value = b"RIFF_FAKE"

    def fake_ffmpeg(cmd):
        out = Path(cmd[-1])
        out.write_bytes(b"ftypisom")
        return 0

    monkeypatch.setattr(
        "app.services.render_compose.run_ffmpeg",
        fake_ffmpeg,
    )
    svc = RenderComposeService(
        frame_repo=frames,
        render_repo=RenderRepository(db_path=db),
        tts=tts,
        media_root=media,
        media_url_prefix="/media",
    )
    result = svc.compose(
        project_id="p1",
        episode_id="__all__",
        engine="edge",
        voice_enabled=True,
        subtitle_enabled=False,
    )
    assert result["output_url"].startswith("/media/")
    assert "render_id" in result


def test_compose_uses_video_segment_when_frame_has_video(tmp_path: Path, monkeypatch):
    db = tmp_path / "r.db"
    media = tmp_path / "media"
    media.mkdir()
    vdir = media / "videos"
    vdir.mkdir()
    frames = FrameRepository(db_path=db)
    # static gpng that must NOT be used when a video exists
    img = media / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    vid = vdir / "clip.mp4"
    vid.write_bytes(b"ftypisom-fake-video")
    frames.create(
        "p1",
        scene_id="s1",
        image_url="/media/a.png",
        video_url="/media/videos/clip.mp4",
        duration=4,
        lines=[],
    )

    calls: list[list[str]] = []

    def fake_ffmpeg(cmd):
        calls.append(cmd)
        out = Path(cmd[-1])
        out.write_bytes(b"ftypisom")
        return 0

    monkeypatch.setattr(
        "app.services.render_compose.run_ffmpeg",
        fake_ffmpeg,
    )
    svc = RenderComposeService(
        frame_repo=frames,
        render_repo=RenderRepository(db_path=db),
        tts=MagicMock(),
        media_root=media,
        media_url_prefix="/media",
    )
    svc.compose(
        project_id="p1",
        episode_id="__all__",
        voice_enabled=False,
    )
    # the segment builder must have received the video file, not the png
    found_video = any(
        str(vid) in [str(x) for x in c] or "clip.mp4" in " ".join(c).replace("\\", "/")
        for c in calls
    )
    found_png_seg = any("a.png" in " ".join(c).replace("\\", "/") for c in calls)
    assert found_video, f"expected the i2v clip to be used; calls={calls}"
    assert not found_png_seg, f"static png must be skipped when video exists; calls={calls}"


def test_escape_vf_path_escapes_colons():
    svc = RenderComposeService.__new__(RenderComposeService)
    assert (
        svc._escape_vf_path(Path(r"C:\Users\AppData\Local\subs.srt"))
        == "'C\\:/Users/AppData/Local/subs.srt'"
    )
    # Posix paths unchanged (no drive colon to escape)
    assert svc._escape_vf_path(Path("/tmp/subs.srt")) == "'/tmp/subs.srt'"
