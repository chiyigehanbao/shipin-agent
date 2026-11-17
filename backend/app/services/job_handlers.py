from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.repositories.scenes import SceneRepository
from app.services.script_expand import ScriptExpandError


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _apply_polish_result(
    *,
    project_id: str,
    target: str,
    target_id: str,
    result: dict[str, Any],
) -> None:
    prompt_en = result.get("prompt_en") or ""
    avoid = result.get("avoid") or result.get("negative_prompt") or ""
    interpretation = result.get("interpretation_cn") or ""
    if target == "scene":
        SceneRepository().update(
            project_id,
            target_id,
            prompt_en=prompt_en,
            negative_prompt=avoid,
            interpretation_cn=interpretation,
        )
        return
    if target == "asset":
        from app.services.runtime import store

        store.update(
            project_id,
            target_id,
            prompt_en=prompt_en,
            negative_prompt=avoid,
            **(
                {"lock_en": result["lock_en"]}
                if result.get("lock_en")
                else {}
            ),
        )
        return
    if target == "frame":
        from app.services.runtime import storyboard_store

        storyboard_store.update(
            project_id,
            target_id,
            prompt_en=prompt_en,
            negative_prompt=avoid,
            **(
                {"motion_prompt_en": result["motion_prompt_en"]}
                if result.get("motion_prompt_en")
                else {}
            ),
        )
        return
    raise ValueError(f"unknown polish target: {target}")


def _handle_polish_one(job_id: str, project_id: str, item: dict[str, Any]) -> dict:
    from app.api.prompts import run_polish
    from app.services.runtime import job_repo

    result = run_polish(
        stage=item.get("stage") or "script_scene",
        text_cn=item.get("text_cn") or "",
        text_en=item.get("text_en") or "",
        context=item.get("context") or {},
        return_interpretation=bool(item.get("return_interpretation", True)),
    )
    if item.get("apply"):
        _apply_polish_result(
            project_id=project_id,
            target=item.get("target") or "scene",
            target_id=item.get("target_id") or "",
            result=result if isinstance(result, dict) else result.__dict__,
        )
    # normalize pydantic / dict
    if hasattr(result, "model_dump"):
        out = result.model_dump()
    elif isinstance(result, dict):
        out = result
    else:
        out = {
            "prompt_en": getattr(result, "prompt_en", ""),
            "avoid": getattr(result, "avoid", ""),
            "interpretation_cn": getattr(result, "interpretation_cn", ""),
        }
    job_repo.update(job_id, progress=90)
    return out


def dispatch_job(job: dict[str, Any]) -> dict[str, Any]:
    from app.services.runtime import job_repo

    t = job.get("type")
    p = job.get("payload") or {}
    pid = job.get("project_id") or ""
    jid = job["id"]

    if t == "script_expand":
        from app.api.scripts import run_expand_persist

        job_repo.update(jid, progress=30)
        try:
            stats = run_expand_persist(pid, p.get("text") or "", p.get("style") or "")
        except ScriptExpandError as e:
            raise RuntimeError(str(e)) from e
        return {"scene_count": stats["scene_count"]}

    if t == "script_analyze":
        from app.api.scripts import run_analyze_persist

        job_repo.update(jid, progress=30)
        try:
            stats = run_analyze_persist(pid, p.get("text") or "", p.get("style") or "")
        except ScriptExpandError as e:
            raise RuntimeError(str(e)) from e
        return {"scene_count": stats["scene_count"]}

    if t == "prompt_polish":
        out = _handle_polish_one(jid, pid, p)
        return {
            "prompt_en": out.get("prompt_en", ""),
            "target_id": p.get("target_id"),
        }

    if t == "prompt_polish_batch":
        items = p.get("items") or []
        done = 0
        for i, item in enumerate(items):
            _handle_polish_one(jid, pid, item)
            done += 1
            prog = int(10 + 80 * (i + 1) / max(len(items), 1))
            job_repo.update(jid, progress=prog)
        return {"count": done}

    if t == "identity_reference_generate":
        from app.services.runtime import identity_reference_generator

        job_repo.update(jid, progress=20)
        return identity_reference_generator.run(
            project_id=pid,
            asset_id=p.get("asset_id") or "",
            seed=p.get("seed"),
        )

    if t == "storyboard_breakdown":
        from app.db.repositories.frames import FrameRepository
        from app.db.repositories.scenes import SceneRepository
        from app.services.llm_runtime import build_llm_provider
        from app.services.storyboard_breakdown import (
            StoryboardBreakdownError,
            StoryboardBreakdownService,
        )

        job_repo.update(jid, progress=30)
        svc = StoryboardBreakdownService(
            llm=build_llm_provider(),
            scene_repo=SceneRepository(),
            frame_repo=FrameRepository(),
        )
        try:
            return svc.run(
                project_id=pid,
                mode=p.get("mode") or "replace_empty",
                scene_ids=p.get("scene_ids"),
            )
        except StoryboardBreakdownError as e:
            raise RuntimeError(str(e)) from e

    if t == "render_compose":
        from app.services.render_compose import RenderComposeError, RenderComposeService

        job_repo.update(jid, progress=20)
        try:
            svc = RenderComposeService()
            return svc.compose(
                project_id=pid,
                episode_id=p.get("episode_id") or "__all__",
                scene_id=p.get("scene_id"),
                engine=p.get("engine") or "edge",
                voice_enabled=bool(p.get("voice_enabled", True)),
                subtitle_enabled=bool(p.get("subtitle_enabled", False)),
                resolution=p.get("resolution") or "1080p",
                fps=int(p.get("fps") or 24),
                bgm_enabled=bool(p.get("bgm_enabled", False)),
                bgm_caption=p.get("bgm_caption") or "",
            )
        except RenderComposeError as e:
            raise RuntimeError(str(e)) from e

    if t == "video_generate":
        from app.services.runtime import client
        from app.services.video_generate import VideoGenerateError, run_video_generate

        def _prog(n: int) -> None:
            job_repo.update(jid, progress=n)

        job_repo.update(jid, progress=10)
        try:
            result = run_video_generate(
                project_id=pid,
                job_id=jid,
                prompt_en=p.get("prompt_en") or "",
                client=client,
                mode=p.get("mode") or "t2v",
                width=int(p.get("width") or 960),
                height=int(p.get("height") or 544),
                length=int(p.get("length") or 124),
                seed=p.get("seed"),
                first_frame_path=p.get("first_frame_path"),
                progress_cb=_prog,
            )
        except VideoGenerateError as e:
            frame_id = p.get("frame_id")
            if frame_id:
                from app.services.runtime import storyboard_store

                storyboard_store.update(
                    pid,
                    frame_id,
                    video_status="failed",
                    video_error=str(e),
                )
            raise RuntimeError(str(e)) from e

        frame_id = p.get("frame_id")
        if frame_id:
            from app.services.runtime import storyboard_store

            storyboard_store.update(
                pid,
                frame_id,
                video_url=result.get("output_url"),
                video_status="completed",
                video_error=None,
            )
        return result

    if t in ("asset_generate", "storyboard_generate"):
        # Linked jobs are driven by AssetQueue; should not be enqueued here.
        raise RuntimeError(f"{t} must be linked to AssetQueue, not JobQueue")

    raise NotImplementedError(f"unhandled job type: {t}")
