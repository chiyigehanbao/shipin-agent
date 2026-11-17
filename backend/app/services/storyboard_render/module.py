from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from app.services.storyboard_render.compiler import (
    _selected_reference,
    compile_render_request,
)
from app.services.storyboard_render.types import (
    RenderPolicy,
    StoryboardRenderError,
    StoryboardRenderRequest,
)


REJECTION_REASONS = {
    "identity_drift",
    "appearance_unrefined",
    "wrong_temperament",
    "wrong_look_state",
    "wrong_action",
    "wrong_composition",
    "other",
}


class StoryboardRenderModule:
    def __init__(
        self,
        *,
        frames: Any,
        scenes: Any,
        assets: Any,
        requests: Any,
        attempts: Any,
        jobs: Any,
        visual_bible: Any,
        client: Any,
        adapters: dict[str, Any],
        enqueue: Callable[[str], None],
        media_root: Path,
        models_dir: Path,
    ) -> None:
        self.frames = frames
        self.scenes = scenes
        self.assets = assets
        self.requests = requests
        self.attempts = attempts
        self.jobs = jobs
        self.visual_bible = visual_bible
        self.client = client
        self.adapters = adapters
        self.enqueue = enqueue
        self.media_root = Path(media_root)
        self.models_dir = Path(models_dir)

    def _resolve_media_path(self, public_url: str) -> Path:
        path = unquote(urlparse(public_url).path)
        if not path.startswith("/media/"):
            raise StoryboardRenderError(
                "reference_upload_invalid",
                f"参考图地址不是本地 media URL：{public_url}",
                field="reference_image_url",
            )
        root = self.media_root.resolve()
        resolved = (root / path.removeprefix("/media/")).resolve()
        if root != resolved and root not in resolved.parents:
            raise StoryboardRenderError(
                "reference_upload_invalid",
                "参考图地址越出 media 目录",
                field="reference_image_url",
            )
        return resolved

    def _assets_with_reference_hashes(self, project_id: str) -> list[dict[str, Any]]:
        resolved_assets: list[dict[str, Any]] = []
        for source in self.assets.list(project_id):
            asset = dict(source)
            image_url, _source_type, _version, _legacy = _selected_reference(asset)
            if image_url:
                try:
                    path = self._resolve_media_path(image_url)
                    asset["reference_image_hash"] = (
                        f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
                    )
                except (OSError, StoryboardRenderError):
                    asset["reference_image_hash"] = ""
            resolved_assets.append(asset)
        return resolved_assets

    def _compile_current(
        self, project_id: str, frame_id: str, policy: RenderPolicy
    ) -> StoryboardRenderRequest:
        frame = self.frames.get(project_id, frame_id)
        if frame is None:
            raise StoryboardRenderError(
                "frame_not_found", "分镜不存在", status_code=404, field="frame_id"
            )
        scenes = self.scenes.list_by_project(project_id)
        scene = next(
            (
                item
                for item in scenes
                if item.get("id") == frame.get("scene_id")
                or item.get("name") == frame.get("scene")
            ),
            {},
        )
        return compile_render_request(
            project_id=project_id,
            frame=frame,
            scene=scene,
            assets=self._assets_with_reference_hashes(project_id),
            visual_bible=self.visual_bible.get(project_id),
            policy=policy,
        )

    def compile(
        self, project_id: str, frame_id: str, policy: RenderPolicy
    ) -> dict[str, Any]:
        request = self._compile_current(project_id, frame_id, policy)
        return self.requests.create(
            project_id=project_id,
            frame_id=frame_id,
            source_hash=request.source_hash,
            request=request.model_dump(mode="json"),
            validation=request.validation.model_dump(mode="json"),
        )

    @staticmethod
    def _raise_invalid(request: StoryboardRenderRequest) -> None:
        if request.validation.valid:
            return
        issue = request.validation.issues[0]
        raise StoryboardRenderError(
            issue.code,
            issue.message,
            status_code=422,
            field=issue.field,
        )

    def _preflight(self, request: StoryboardRenderRequest, adapter: Any) -> None:
        if not self.client.health():
            raise StoryboardRenderError(
                "comfyui_unavailable", "ComfyUI 当前不可用", status_code=503
            )
        available_nodes: set[str] = set()
        if adapter.name == "flux_kontext":
            try:
                available_nodes = self.client.available_node_types()
            except Exception as exc:
                raise StoryboardRenderError(
                    "kontext_workflow_unavailable",
                    f"无法读取 ComfyUI 节点清单：{exc}",
                    status_code=503,
                ) from exc
        readiness = adapter.preflight(
            request=request,
            models_dir=self.models_dir,
            available_node_types=available_nodes,
        )
        if readiness.ready:
            return
        if readiness.missing_files:
            raise StoryboardRenderError(
                "kontext_model_unavailable",
                "缺少模型文件：" + ", ".join(readiness.missing_files),
                status_code=409,
                field="models",
            )
        if readiness.missing_nodes:
            raise StoryboardRenderError(
                "kontext_workflow_unavailable",
                "ComfyUI 缺少节点：" + ", ".join(readiness.missing_nodes),
                status_code=409,
                field="nodes",
            )
        code = readiness.issues[0] if readiness.issues else "kontext_workflow_unavailable"
        raise StoryboardRenderError(code, "渲染预检未通过", status_code=409)

    def submit(
        self,
        project_id: str,
        frame_id: str,
        *,
        policy: RenderPolicy,
        seed: int | None = None,
    ) -> dict[str, Any]:
        request_row = self.compile(project_id, frame_id, policy)
        request = StoryboardRenderRequest.model_validate(request_row["request"])
        self._raise_invalid(request)
        adapter_key = (
            "text_only_flux"
            if request.render_policy.allow_temporary_degradation
            else "flux_kontext"
        )
        adapter = self.adapters[adapter_key]
        self._preflight(request, adapter)
        frame = self.frames.get(project_id, frame_id)
        assert frame is not None
        asset = self.assets.create(
            project_id=project_id,
            name=f"分镜 {frame.get('number') or frame_id} 候选",
            type="storyboard",
            prompt_cn=str(frame.get("prompt_cn") or ""),
            prompt_en=request.compiled_prompt,
            negative_prompt=request.negative_prompt,
            model="flux",
            status="generating",
            aspect="landscape",
        )
        attempt = self.attempts.create(
            request_id=request_row["id"],
            project_id=project_id,
            frame_id=frame_id,
            asset_id=asset["id"],
            adapter=adapter.name,
            workflow_version=adapter.workflow_version,
            model_fingerprint=adapter.model_fingerprint,
            seed=int(seed if seed is not None else random.randint(0, 2**31 - 1)),
            is_degraded=adapter.name == "text_only_flux",
        )
        job = self.jobs.create(
            type="storyboard_render",
            project_id=project_id,
            title=f"分镜渲染 · {frame.get('number') or frame_id}",
            payload={"attempt_id": attempt["id"], "frame_id": frame_id},
            link_path=f"/workbench/{project_id}/storyboard",
        )
        attempt = self.attempts.attach_job(attempt["id"], job["id"])
        self.frames.update(project_id, frame_id, status="generating", error=None)
        self.enqueue(attempt["id"])
        return attempt

    def get_state(self, project_id: str, frame_id: str) -> dict[str, Any]:
        frame = self.frames.get(project_id, frame_id)
        if frame is None:
            raise StoryboardRenderError(
                "frame_not_found", "分镜不存在", status_code=404, field="frame_id"
            )
        latest = self.requests.latest_for_frame(project_id, frame_id)
        policy_data = ((latest or {}).get("request") or {}).get("render_policy") or {}
        policy = RenderPolicy.model_validate(policy_data)
        current = self._compile_current(project_id, frame_id, policy)
        return {
            "frame_id": frame_id,
            "accepted_render_attempt_id": frame.get("accepted_render_attempt_id"),
            "latest_request": latest,
            "current_request": current.model_dump(mode="json"),
            "attempts": self.attempts.list_for_frame(project_id, frame_id),
            "stale": bool(latest and latest["source_hash"] != current.source_hash),
        }

    def _owned_attempt(
        self, project_id: str, frame_id: str, attempt_id: str
    ) -> dict[str, Any]:
        attempt = self.attempts.get(attempt_id)
        if (
            not attempt
            or attempt["project_id"] != project_id
            or attempt["frame_id"] != frame_id
        ):
            raise StoryboardRenderError(
                "render_attempt_not_found", "渲染尝试不存在", status_code=404
            )
        return attempt

    def accept(
        self, project_id: str, frame_id: str, attempt_id: str
    ) -> dict[str, Any]:
        attempt = self._owned_attempt(project_id, frame_id, attempt_id)
        if attempt["status"] != "candidate" or not attempt.get("image_url"):
            raise StoryboardRenderError(
                "render_candidate_required", "只有候选图片可以被接受", status_code=409
            )
        frame = self.frames.get(project_id, frame_id)
        assert frame is not None
        previous_id = frame.get("accepted_render_attempt_id")
        if previous_id and previous_id != attempt_id:
            previous = self.attempts.get(previous_id)
            if previous and previous.get("status") == "accepted":
                self.attempts.transition(previous_id, "superseded")
        accepted = self.attempts.transition(attempt_id, "accepted")
        self.frames.update(
            project_id,
            frame_id,
            accepted_render_attempt_id=attempt_id,
            asset_id=attempt.get("asset_id"),
            image_url=attempt["image_url"],
            status="completed",
            error=None,
        )
        return accepted

    def reject(
        self,
        project_id: str,
        frame_id: str,
        attempt_id: str,
        reason: str,
        note: str,
    ) -> dict[str, Any]:
        if reason not in REJECTION_REASONS:
            raise StoryboardRenderError(
                "invalid_rejection_reason", "未知的驳回原因", status_code=422
            )
        self._owned_attempt(project_id, frame_id, attempt_id)
        return self.attempts.transition(
            attempt_id,
            "rejected",
            rejection_reason=reason,
            rejection_note=note.strip(),
        )

    def retry(
        self,
        project_id: str,
        frame_id: str,
        attempt_id: str,
        *,
        reuse_seed: bool = False,
    ) -> dict[str, Any]:
        attempt = self._owned_attempt(project_id, frame_id, attempt_id)
        request_row = self.requests.get(attempt["request_id"])
        if request_row is None:
            raise StoryboardRenderError(
                "render_attempt_not_found", "渲染请求不存在", status_code=404
            )
        policy = RenderPolicy.model_validate(request_row["request"]["render_policy"])
        return self.submit(
            project_id,
            frame_id,
            policy=policy,
            seed=attempt["seed"] if reuse_seed else None,
        )
