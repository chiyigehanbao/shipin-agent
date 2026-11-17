# Compose static storyboard frames + TTS into an mp4 via ffmpeg
from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from app.core.settings import settings
from app.db.repositories.frames import FrameRepository
from app.db.repositories.renders import RenderRepository
from app.services.tts import get_tts_provider
from app.services.tts_settings_store import TtsSettingsStore, default_tts_settings_path


class RenderComposeError(RuntimeError):
    pass


def run_ffmpeg(cmd: list[str]) -> int:
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RenderComposeError(
            f"ffmpeg failed ({completed.returncode}): {completed.stderr[-800:]}"
        )
    return completed.returncode


def _ffmpeg_bin() -> str:
    import os

    return os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg") or "ffmpeg"


def _resolve_image_path(image_url: str, media_root: Path) -> Path:
    # image_url like /media/assets/xxx.png → media_root/assets/xxx.png
    url = image_url.replace("\\", "/")
    if url.startswith("/media/"):
        rel = url[len("/media/") :]
        return media_root / rel
    p = Path(url)
    if p.is_file():
        return p
    return media_root / url.lstrip("/")


class RenderComposeService:
    def __init__(
        self,
        *,
        frame_repo: FrameRepository | None = None,
        render_repo: RenderRepository | None = None,
        tts: Any = None,
        media_root: Path | None = None,
        media_url_prefix: str = "/media",
    ) -> None:
        self.frame_repo = frame_repo or FrameRepository()
        self.render_repo = render_repo or RenderRepository()
        self.tts = tts
        self.media_root = media_root or settings.media_mount_dir
        self.media_url_prefix = media_url_prefix

    def compose(
        self,
        *,
        project_id: str,
        episode_id: str = "__all__",
        scene_id: Optional[str] = None,
        engine: str = "edge",
        voice_enabled: bool = True,
        subtitle_enabled: bool = False,
        resolution: str = "1080p",
        fps: int = 24,
        bgm_enabled: bool = False,
        bgm_caption: str = "",
        ace_step: Any = None,
    ) -> dict[str, Any]:
        del resolution  # reserved; scale not required for MVP
        frames = self.frame_repo.list(project_id)
        sid = scene_id
        if episode_id and episode_id != "__all__":
            sid = episode_id
        if sid:
            frames = [f for f in frames if f.get("scene_id") == sid]
        usable = [f for f in frames if f.get("image_url") or f.get("video_url")]
        if not usable:
            missing = [f"#{f.get('number')}({f.get('id')})" for f in frames]
            raise RenderComposeError(
                f"没有可合成的分镜（{len(frames)} 帧均缺图或未生成视频）：{', '.join(missing[:12])}"
            )
        frames = usable

        tts = self.tts
        if tts is None:
            cfg = TtsSettingsStore(default_tts_settings_path()).get()
            tts = get_tts_provider(engine or cfg["engine"], voice=cfg.get("edge_voice"))

        work = Path(tempfile.mkdtemp(prefix="vf_render_"))
        try:
            seg_files: list[Path] = []
            srt_lines: list[str] = []
            cursor = 0.0
            warnings: list[str] = []
            clips_used = 0

            for i, fr in enumerate(frames):
                video_path: Path | None = None
                if fr.get("video_url"):
                    vp = _resolve_image_path(fr["video_url"], self.media_root)
                    if vp.is_file():
                        video_path = vp
                    else:
                        warnings.append(f"missing video {fr['video_url']}")
                img = None
                if fr.get("image_url"):
                    img = _resolve_image_path(fr["image_url"], self.media_root)
                    if not img.is_file():
                        warnings.append(f"missing image {fr['image_url']}")
                        img = None
                if video_path is None and img is None:
                    continue

                base_dur = float(fr.get("duration") or 3.0)
                audio_path: Path | None = None
                audio_dur = 0.0
                lines = fr.get("lines") or []
                if voice_enabled and lines:
                    chunks: list[bytes] = []
                    for ln in lines:
                        try:
                            chunks.append(
                                tts.synthesize(
                                    text=ln.get("text") or "",
                                    emotion=ln.get("emotion") or "",
                                    speaker=ln.get("speaker") or "",
                                )
                            )
                        except Exception as e:
                            warnings.append(f"tts fail frame={fr['id']}: {e}")
                    if chunks:
                        audio_path = work / f"a_{i}.mp3"
                        # concatenate mp3 bytes naively (works for same codec edge output)
                        audio_path.write_bytes(b"".join(chunks))
                        audio_dur = max(base_dur, self._probe_duration(audio_path) or base_dur)

                if video_path is not None:
                    clip_dur = self._probe_duration(video_path) or base_dur
                    dur = max(audio_dur if audio_path else clip_dur, 0.5)
                    clips_used += 1
                else:
                    dur = max(audio_dur if audio_path else base_dur, 0.5)
                if subtitle_enabled and lines:
                    for ln in lines:
                        start = cursor
                        end = cursor + dur / max(len(lines), 1)
                        srt_lines.append(
                            self._srt_block(
                                len(srt_lines) + 1,
                                start,
                                end,
                                f"{ln.get('speaker') or ''}：{ln.get('text') or ''}".strip("："),
                            )
                        )
                seg = work / f"seg_{i}.mp4"
                if video_path is not None:
                    burned = work / f"av_{i}.mp4"
                    self._mix_audio(video_path, audio_path, burned)
                    seg_files.append(burned)
                else:
                    self._make_segment(img, audio_path, dur, fps, seg)
                    seg_files.append(seg)
                cursor += dur

            if not seg_files:
                detail = "；".join(warnings[:8]) if warnings else ""
                raise RenderComposeError(
                    f"所有分镜图均不可用" + (f"（{detail}）" if detail else "")
                )

            list_file = work / "list.txt"
            list_file.write_text(
                "\n".join(f"file '{p.as_posix()}'" for p in seg_files),
                encoding="utf-8",
            )
            out_dir = self.media_root / "renders" / project_id
            out_dir.mkdir(parents=True, exist_ok=True)
            out_name = f"{uuid.uuid4().hex[:10]}.mp4"
            out_path = out_dir / out_name
            cmd = [
                _ffmpeg_bin(),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(out_path),
            ]
            if subtitle_enabled and srt_lines:
                srt_path = work / "subs.srt"
                srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
                # re-encode with subtitles
                burned = work / "burned.mp4"
                run_ffmpeg(
                    [
                        _ffmpeg_bin(),
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(list_file),
                        "-vf",
                        f"subtitles={self._escape_vf_path(srt_path)}",
                        "-c:a",
                        "copy",
                        str(burned),
                    ]
                )
                shutil.copy2(burned, out_path)
            else:
                run_ffmpeg(cmd)

            bgm_path = self._maybe_generate_bgm(
                ace_step, bgm_enabled, bgm_caption, cursor, work, warnings
            )
            if bgm_path is not None:
                out_path = self._mix_bgm(out_path, bgm_path, work)

            output_url = f"{self.media_url_prefix}/renders/{project_id}/{out_name}"
            row = self.render_repo.create(
                project_id=project_id,
                scene_id=sid,
                status="completed",
                engine=engine,
                output_url=output_url,
                duration_sec=cursor,
            )
            return {
                "render_id": row["id"],
                "output_url": output_url,
                "duration_sec": cursor,
                "warnings": warnings,
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _maybe_generate_bgm(
        self,
        ace_step,
        bgm_enabled,
        bgm_caption,
        duration_sec,
        work,
        warnings,
    ) -> Optional[Path]:
        """bgm_enabled 时调用 ACE-Step 生成一段器乐 BGM；不可用则跳过并记录。"""
        if not bgm_enabled:
            return None
        if ace_step is None:
            from app.services import ace_step as ace_step_mod

            ace_step = ace_step_mod
        try:
            if not ace_step.is_available():
                warnings.append("BGM：ACE-Step 未启动或不可用，已跳过配乐")
                return None
            bgm_path = work / "bgm.mp3"
            ace_step.generate_bgm(
                caption=bgm_caption or "",
                duration_sec=float(duration_sec or 3.0) + 4,
                out_path=bgm_path,
            )
            return bgm_path
        except Exception as e:
            warnings.append(f"BGM 生成失败：{e}")
            return None

    def _mix_bgm(self, video: Path, bgm: Path, work: Path) -> Path:
        """把 BGM 作为背景声道，以较低音量混在成片对白/视频音频之下。"""
        mixed = work / "mixed.mp4"
        run_ffmpeg(
            [
                _ffmpeg_bin(),
                "-y",
                "-i",
                str(video),
                "-i",
                str(bgm),
                "-filter_complex",
                "[0:a]volume=1.0[main];"
                "[1:a]volume=0.18,afade=t=in:d=2[bgm];"
                "[main][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]",
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-shortest",
                str(mixed),
            ]
        )
        return mixed

    def _probe_duration(self, path: Path) -> float | None:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None
        try:
            completed = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
            )
            return float(completed.stdout.strip())
        except Exception:
            return None

    def _mix_audio(self, video: Path, audio: Path | None, out: Path) -> None:
        # Real i2v clip is the base; overlay TTS when present. Without audio we
        # re-mux only (same stream params → still compatible with concat -c copy).
        if audio is None or not audio.is_file():
            run_ffmpeg([_ffmpeg_bin(), "-y", "-i", str(video), "-c", "copy", str(out)])
            return
        cmd = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
        run_ffmpeg(cmd)

    def _make_segment(
        self,
        image: Path,
        audio: Path | None,
        duration: float,
        fps: int,
        out: Path,
    ) -> None:
        if audio and audio.is_file():
            cmd = [
                _ffmpeg_bin(),
                "-y",
                "-loop",
                "1",
                "-i",
                str(image),
                "-i",
                str(audio),
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-c:a",
                "aac",
                "-shortest",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                str(out),
            ]
        else:
            cmd = [
                _ffmpeg_bin(),
                "-y",
                "-loop",
                "1",
                "-i",
                str(image),
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v",
                "libx264",
                "-t",
                str(duration),
                "-c:a",
                "aac",
                "-shortest",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                str(out),
            ]
        run_ffmpeg(cmd)

    @staticmethod
    def _escape_vf_path(p: Path) -> str:
        # Windows drive-colon must be escaped for ffmpeg filtergraph, and the
        # whole value single-quoted so remaining ':' in the path stay literal.
        posix = p.as_posix().replace(":", "\\:")
        return f"'{posix}'"

    @staticmethod
    def _srt_block(idx: int, start: float, end: float, text: str) -> str:
        def ts(v: float) -> str:
            h = int(v // 3600)
            m = int((v % 3600) // 60)
            s = int(v % 60)
            ms = int((v - int(v)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        return f"{idx}\n{ts(start)} --> {ts(end)}\n{text}\n"
