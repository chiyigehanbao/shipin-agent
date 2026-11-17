from __future__ import annotations

from pathlib import Path

from app.db.repositories.visual_specs import VisualSpecRepository
from app.services.prompt_ir import ProjectVisualBible


def default_visual_bible() -> ProjectVisualBible:
    return ProjectVisualBible(
        casting_aesthetic=(
            "Polished commercial short-drama casting: harmonious, distinctive, "
            "camera-ready faces with believable age and natural skin texture."
        ),
        realism_policy=[
            "Keep natural pores and material response without plastic skin.",
            "Use flattering motivated light without beauty-filter smoothing.",
        ],
        identity_policy=[
            "Permanent identity contains stable facial proportions, build, and distinctive anchors only.",
            "Do not encode temporary plot conditions as facial identity.",
        ],
        state_policy=[
            "Weather exposure, injury, fatigue, makeup, and wardrobe belong to explicit look or state variants.",
        ],
        cinematography=[
            "Prefer story-motivated composition over centered generic portraits.",
            "Keep lighting direction and spatial geography continuous across shots.",
        ],
        negative_defaults=[
            "plastic skin",
            "beauty filter",
            "generic influencer face",
            "anatomical deformation",
            "text watermark",
        ],
    )


class VisualBibleService:
    def __init__(
        self,
        repo: VisualSpecRepository | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.repo = repo or VisualSpecRepository(db_path)

    def get(self, project_id: str) -> ProjectVisualBible:
        row = self.repo.get(project_id)
        if row is None:
            return default_visual_bible()
        return ProjectVisualBible.model_validate(row["spec_json"])

    def save(self, project_id: str, spec: ProjectVisualBible) -> dict:
        return self.repo.upsert(project_id, spec.model_dump())
