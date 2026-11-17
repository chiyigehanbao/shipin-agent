# ============================================
# 运行时单例（store / client / queue / storyboard_store）
# ============================================
# 进程内共享的资产生成相关组件，由 main.py 在
# startup 时启动 worker。
# ============================================

from app.core.settings import settings
from app.services.asset_queue import AssetQueue
from app.services.asset_store import AssetStore
from app.services.comfy_settings_store import (
    ComfySettingsStore,
    default_comfy_settings_path,
)
from app.services.comfyui_client import ComfyUIClient
from app.services.job_handlers import dispatch_job
from app.services.job_queue import JobQueue
from app.services.storyboard_store import StoryboardStore
from app.services.workflows import build_workflow
from app.db.repositories.jobs import JobRepository
from app.db.repositories.scenes import SceneRepository
from app.db.repositories.storyboard_renders import (
    RenderAttemptRepository,
    RenderRequestRepository,
)
from app.services.storyboard_render.adapters import (
    FluxKontextAdapter,
    TextOnlyFluxAdapter,
)
from app.services.storyboard_render.module import StoryboardRenderModule
from app.services.storyboard_render.worker import StoryboardRenderWorker
from app.services.visual_bible import VisualBibleService
from app.services.identity_reference.face_backend import build_face_backend
from app.services.identity_reference.evaluation import IdentityEvaluationService
from app.services.identity_reference.generation import IdentityReferenceGenerator
from app.services.identity_reference.service import IdentityReferenceService

store = AssetStore()
storyboard_store = StoryboardStore()
face_backend = build_face_backend(settings.face_identity_models_dir)
identity_reference_service = IdentityReferenceService(
    assets=store,
    face_backend=face_backend,
    media_root=settings.media_mount_dir,
    output_root=settings.assets_output_dir,
)
identity_evaluation_service = IdentityEvaluationService(
    face_backend=face_backend,
    media_root=settings.media_mount_dir,
)
comfy_settings = ComfySettingsStore(default_comfy_settings_path())
_saved = comfy_settings.get_base_url()
client = ComfyUIClient(
    base_url=_saved or settings.comfyui_base_url,
    on_base_url_change=comfy_settings.save_base_url,
)
queue = AssetQueue(
    store=store,
    client=client,
    output_root=settings.assets_output_dir,
    build_workflow=build_workflow,
    poll_timeout_sec=settings.poll_timeout_sec,
    poll_interval_sec=settings.poll_interval_sec,
)
job_repo = JobRepository()
job_queue = JobQueue(repo=job_repo, dispatch=dispatch_job)
render_request_repo = RenderRequestRepository()
render_attempt_repo = RenderAttemptRepository()
scene_repo = SceneRepository()
storyboard_render_adapters = {
    "flux_kontext": FluxKontextAdapter(),
    "text_only_flux": TextOnlyFluxAdapter(),
}
identity_reference_generator = IdentityReferenceGenerator(
    assets=store,
    identity_references=identity_reference_service,
    client=client,
    adapter=storyboard_render_adapters["flux_kontext"],
    media_root=settings.media_mount_dir,
    output_root=settings.assets_output_dir,
    poll_timeout_sec=settings.poll_timeout_sec,
    poll_interval_sec=settings.poll_interval_sec,
)
storyboard_render_worker = StoryboardRenderWorker(
    requests=render_request_repo,
    attempts=render_attempt_repo,
    assets=store,
    frames=storyboard_store,
    jobs=job_repo,
    client=client,
    adapters=storyboard_render_adapters,
    output_root=settings.assets_output_dir,
    media_root=settings.media_mount_dir,
    identity_evaluator=identity_evaluation_service,
    poll_timeout_sec=settings.poll_timeout_sec,
    poll_interval_sec=settings.poll_interval_sec,
)
storyboard_render_module = StoryboardRenderModule(
    frames=storyboard_store,
    scenes=scene_repo,
    assets=store,
    requests=render_request_repo,
    attempts=render_attempt_repo,
    jobs=job_repo,
    visual_bible=VisualBibleService(),
    client=client,
    adapters=storyboard_render_adapters,
    enqueue=storyboard_render_worker.enqueue,
    media_root=settings.media_mount_dir,
    models_dir=settings.comfyui_models_dir,
)


def fail_generating_entities(*, error: str = "server_restarted") -> int:
    """Mark in-flight assets/frames failed after process restart."""
    n = 0
    # Frame-based and storyboard-based image generation
    for a in store.list_by_status("generating", limit=500):
        store.update(a["project_id"], a["id"], status="failed", error=error)
        n += 1
    for f in storyboard_store.list_by_status("generating", limit=500):
        storyboard_store.update(f["project_id"], f["id"], status="failed", error=error)
        n += 1

    # Video generation may use multiple transient states across releases; fail any in-flight marker.
    for video_status in ("generating", "queued", "running"):
        for f in storyboard_store.list_by_video_status(video_status, limit=500):
            storyboard_store.update(
                f["project_id"],
                f["id"],
                video_status="failed",
                video_error=error,
            )
            n += 1
    n += render_attempt_repo.fail_inflight(error=error)
    return n
