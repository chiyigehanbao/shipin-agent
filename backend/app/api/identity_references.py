from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.services.identity_reference.service import IdentityReferenceError
from app.services.identity_reference.types import NormalizedCrop


router = APIRouter()


class ConfirmIdentityReferenceBody(BaseModel):
    candidate_id: str


class GenerateIdentityReferenceBody(BaseModel):
    seed: int | None = None


def get_identity_reference_service():
    from app.services.runtime import identity_reference_service

    return identity_reference_service


def get_identity_reference_job_runtime():
    from app.services.runtime import job_queue, job_repo, store

    return job_repo, job_queue, store


def raise_identity_http_error(exc: IdentityReferenceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc


@router.get("/{project_id}/{asset_id}/identity-reference")
def get_identity_reference(project_id: str, asset_id: str):
    try:
        return get_identity_reference_service().get_state(project_id, asset_id)
    except IdentityReferenceError as exc:
        raise_identity_http_error(exc)


@router.post(
    "/{project_id}/{asset_id}/identity-reference/auto",
    status_code=status.HTTP_201_CREATED,
)
def create_auto_identity_reference(project_id: str, asset_id: str):
    try:
        return get_identity_reference_service().create_auto_candidate(
            project_id, asset_id
        )
    except IdentityReferenceError as exc:
        raise_identity_http_error(exc)


@router.post(
    "/{project_id}/{asset_id}/identity-reference/crop",
    status_code=status.HTTP_201_CREATED,
)
def create_cropped_identity_reference(
    project_id: str, asset_id: str, body: NormalizedCrop
):
    try:
        return get_identity_reference_service().create_crop_candidate(
            project_id, asset_id, body
        )
    except IdentityReferenceError as exc:
        raise_identity_http_error(exc)


@router.post(
    "/{project_id}/{asset_id}/identity-reference/upload",
    status_code=status.HTTP_201_CREATED,
)
async def upload_identity_reference(
    project_id: str,
    asset_id: str,
    file: UploadFile = File(...),
):
    try:
        payload = await file.read()
        return get_identity_reference_service().create_upload_candidate(
            project_id,
            asset_id,
            payload,
            filename=file.filename or "identity.png",
        )
    except IdentityReferenceError as exc:
        raise_identity_http_error(exc)
    finally:
        await file.close()


@router.post("/{project_id}/{asset_id}/identity-reference/confirm")
def confirm_identity_reference(
    project_id: str,
    asset_id: str,
    body: ConfirmIdentityReferenceBody,
):
    try:
        return get_identity_reference_service().confirm_candidate(
            project_id, asset_id, body.candidate_id
        )
    except IdentityReferenceError as exc:
        raise_identity_http_error(exc)


@router.post(
    "/{project_id}/{asset_id}/identity-reference/generate",
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_identity_reference(
    project_id: str,
    asset_id: str,
    body: GenerateIdentityReferenceBody,
):
    job_repo, job_queue, assets = get_identity_reference_job_runtime()
    asset = assets.get(project_id, asset_id)
    if asset is None or asset.get("type") != "character":
        raise HTTPException(status_code=404, detail="人物资产不存在")
    if (
        asset.get("status") != "completed"
        or asset.get("selection_status") != "selected"
        or not asset.get("image_url")
    ):
        raise HTTPException(status_code=409, detail="请先选择一个已完成的人物定妆资产")
    job = job_repo.create(
        type="identity_reference_generate",
        project_id=project_id,
        title=f"标准身份照 · {asset['name']}",
        payload={"asset_id": asset_id, "seed": body.seed},
        link_path=f"/workbench/{project_id}/assets",
    )
    job_queue.enqueue(job["id"])
    return job
