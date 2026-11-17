from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.services.identity_reference.service import (
    IdentityReferenceError,
    IdentityReferenceService,
)
from app.services.storyboard_render.types import (
    CharacterIdentity,
    RenderPolicy,
    RenderValidation,
    StoryboardRenderRequest,
)


IDENTITY_PORTRAIT_PROMPT = (
    "Create a standardized identity portrait of the exact same person from reference "
    "image 1. Neutral expression, direct eye contact, head and shoulders, centered, "
    "plain neutral background, even soft frontal lighting, and natural skin texture. "
    "Preserve facial geometry, age impression, stable hairline, and hairstyle. Replace "
    "wardrobe with a simple neutral crew-neck top. No scene context, props, dramatic "
    "lighting, expressive pose, or stylization."
)


class IdentityReferenceGenerator:
    def __init__(
        self,
        *,
        assets: Any,
        identity_references: IdentityReferenceService,
        client: Any,
        adapter: Any,
        media_root: Path,
        output_root: Path,
        poll_timeout_sec: float = 600.0,
        poll_interval_sec: float = 1.5,
    ) -> None:
        self.assets = assets
        self.identity_references = identity_references
        self.client = client
        self.adapter = adapter
        self.media_root = Path(media_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.poll_timeout_sec = poll_timeout_sec
        self.poll_interval_sec = poll_interval_sec

    def _resolve_media_url(self, public_url: str) -> Path:
        url_path = unquote(urlparse(public_url).path)
        if not url_path.startswith("/media/"):
            raise IdentityReferenceError(
                "identity_reference_invalid",
                "身份生成输入不是本地媒体文件。",
                status_code=422,
            )
        resolved = (self.media_root / url_path.removeprefix("/media/")).resolve()
        if not resolved.is_relative_to(self.media_root) or not resolved.is_file():
            raise IdentityReferenceError(
                "identity_reference_invalid",
                "身份生成输入文件不存在或路径无效。",
                status_code=422,
            )
        return resolved

    @staticmethod
    def _request(
        *,
        project_id: str,
        asset: dict[str, Any],
        source_url: str,
        source_hash: str,
        source_type: str,
        version: int,
    ) -> StoryboardRenderRequest:
        identity = asset.get("identity") or {}
        character = CharacterIdentity(
            character_asset_id=str(asset["id"]),
            character_name=str(asset.get("name") or asset["id"]),
            reference_asset_id=str(asset["id"]),
            reference_image_url=source_url,
            reference_image_hash=source_hash,
            identity_anchor=str(
                identity.get("identity_anchor") or asset.get("lock_en") or ""
            ),
            reference_order=1,
            legacy_reference=source_type == "legacy_full_reference",
            reference_source_type=source_type,
            reference_version=version,
        )
        request_hash = hashlib.sha256(
            f"{asset['id']}:{source_hash}:{version}:{IDENTITY_PORTRAIT_PROMPT}".encode(
                "utf-8"
            )
        ).hexdigest()
        return StoryboardRenderRequest(
            project_id=project_id,
            frame_id=f"identity:{asset['id']}",
            character_identities=[character],
            look_states=[],
            weak_characters=[],
            scene_spec={"background": "plain neutral background"},
            shot_spec={"shot_type": "centered head-and-shoulders portrait"},
            render_policy=RenderPolicy(),
            compiled_prompt=IDENTITY_PORTRAIT_PROMPT,
            negative_prompt=(
                "different person, identity drift, elaborate wardrobe, scene background, "
                "dramatic lighting, exaggerated expression, plastic skin"
            ),
            width=768,
            height=768,
            source_hash=request_hash,
            validation=RenderValidation(valid=True, issues=[]),
        )

    def run(
        self, *, project_id: str, asset_id: str, seed: int | None = None
    ) -> dict[str, Any]:
        state = self.identity_references.get_state(project_id, asset_id)
        asset = self.assets.get(project_id, asset_id)
        if asset is None:
            raise IdentityReferenceError(
                "identity_asset_not_found", "人物资产不存在。", status_code=404
            )
        reference = state.get("reference") or {}
        if reference.get("status") == "ready" and reference.get("image_url"):
            source_url = str(reference["image_url"])
            source_type = str(reference.get("source_type") or "manual_crop")
            version = int(reference.get("version") or 1)
        else:
            source_url = str(asset.get("image_url") or "")
            source_type = "legacy_full_reference"
            version = 0
        source_path = self._resolve_media_url(source_url)
        source_hash = f"sha256:{hashlib.sha256(source_path.read_bytes()).hexdigest()}"
        request = self._request(
            project_id=project_id,
            asset=asset,
            source_url=source_url,
            source_hash=source_hash,
            source_type=source_type,
            version=version,
        )
        actual_seed = int(seed if seed is not None else 42)
        uploaded = self.client.upload_image(source_path)
        workflow = self.adapter.build(
            request=request,
            uploaded_images=[uploaded],
            seed=actual_seed,
        )
        prompt_id = self.client.submit_workflow(workflow)
        meta = self.client.poll_history(
            prompt_id,
            timeout_sec=self.poll_timeout_sec,
            interval_sec=self.poll_interval_sec,
        )
        temporary = (
            self.output_root
            / project_id
            / "identity"
            / f".generated-{uuid.uuid4().hex[:12]}.png"
        )
        temporary.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.client.download_image(meta, temporary)
            candidate = self.identity_references.register_generated(
                project_id,
                asset_id,
                temporary,
                source_image_url=source_url,
            )
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "candidate": candidate,
            "seed": actual_seed,
            "source_image_url": source_url,
        }
