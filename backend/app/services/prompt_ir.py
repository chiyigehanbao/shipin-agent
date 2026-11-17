from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectVisualBible(BaseModel):
    version: int = 1
    casting_aesthetic: str
    realism_policy: list[str] = Field(default_factory=list)
    identity_policy: list[str] = Field(default_factory=list)
    state_policy: list[str] = Field(default_factory=list)
    cinematography: list[str] = Field(default_factory=list)
    negative_defaults: list[str] = Field(default_factory=list)


class H3SourceContext(BaseModel):
    mode: Literal["t2va", "i2va"]
    duration_sec: float
    project: dict[str, Any] = Field(default_factory=dict)
    visual_bible: ProjectVisualBible
    subjects: list[dict[str, Any]] = Field(default_factory=list)
    scene: dict[str, Any] = Field(default_factory=dict)
    shot: dict[str, Any] = Field(default_factory=dict)
    dialogue: list[dict[str, Any]] = Field(default_factory=list)
    soundscape: str = ""
    music: str = ""
