from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.storyboard_render.types import RenderPolicy, StoryboardRenderError


router = APIRouter()


class SubmitRenderBody(BaseModel):
    seed: int | None = None
    temporary_degradation: bool = False


class RejectRenderBody(BaseModel):
    reason: Literal[
        "identity_drift",
        "appearance_unrefined",
        "wrong_temperament",
        "wrong_look_state",
        "wrong_action",
        "wrong_composition",
        "other",
    ]
    note: str = ""


class RetryRenderBody(BaseModel):
    reuse_seed: bool = False


def get_storyboard_render_module():
    from app.services.runtime import storyboard_render_module

    return storyboard_render_module


def raise_render_http_error(exc: StoryboardRenderError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message, "field": exc.field},
    ) from exc


@router.get("/{project_id}/frames/{frame_id}/render-state")
def render_state(project_id: str, frame_id: str):
    try:
        return get_storyboard_render_module().get_state(project_id, frame_id)
    except StoryboardRenderError as exc:
        raise_render_http_error(exc)


@router.post(
    "/{project_id}/frames/{frame_id}/render",
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_render(project_id: str, frame_id: str, body: SubmitRenderBody):
    policy = RenderPolicy(
        allow_temporary_degradation=body.temporary_degradation
    )
    try:
        return get_storyboard_render_module().submit(
            project_id,
            frame_id,
            policy=policy,
            seed=body.seed,
        )
    except StoryboardRenderError as exc:
        raise_render_http_error(exc)


@router.post(
    "/{project_id}/frames/{frame_id}/render-attempts/{attempt_id}/accept"
)
def accept_render(project_id: str, frame_id: str, attempt_id: str):
    try:
        return get_storyboard_render_module().accept(project_id, frame_id, attempt_id)
    except StoryboardRenderError as exc:
        raise_render_http_error(exc)


@router.post(
    "/{project_id}/frames/{frame_id}/render-attempts/{attempt_id}/reject"
)
def reject_render(
    project_id: str,
    frame_id: str,
    attempt_id: str,
    body: RejectRenderBody,
):
    try:
        return get_storyboard_render_module().reject(
            project_id,
            frame_id,
            attempt_id,
            body.reason,
            body.note,
        )
    except StoryboardRenderError as exc:
        raise_render_http_error(exc)


@router.post(
    "/{project_id}/frames/{frame_id}/render-attempts/{attempt_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_render(
    project_id: str,
    frame_id: str,
    attempt_id: str,
    body: RetryRenderBody,
):
    try:
        return get_storyboard_render_module().retry(
            project_id,
            frame_id,
            attempt_id,
            reuse_seed=body.reuse_seed,
        )
    except StoryboardRenderError as exc:
        raise_render_http_error(exc)
