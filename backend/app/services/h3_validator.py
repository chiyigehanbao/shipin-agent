from __future__ import annotations

import re

from pydantic import BaseModel, Field


I2VA_ALIGNMENT = (
    "For the target video, at 0.00 seconds into the target video, "
    "<Picture 1> (from [Shot 1]) is fully referenced."
)
_FIELDS = [
    "integrated_multimodal_description",
    "overall_soundscape",
    "non_diegetic_music",
]


class H3ValidationIssue(BaseModel):
    code: str
    message: str
    severity: str = "error"


class H3ValidationReport(BaseModel):
    valid: bool
    issues: list[H3ValidationIssue] = Field(default_factory=list)


def _issue(issues: list[H3ValidationIssue], code: str, message: str) -> None:
    issues.append(H3ValidationIssue(code=code, message=message))


def _seconds(minutes: str, seconds: str, milliseconds: str) -> float:
    return int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


def validate_h3_prompt(
    content: str,
    *,
    mode: str,
    duration_sec: float,
    expected_dialogue: list[str] | None = None,
) -> H3ValidationReport:
    text = (content or "").strip()
    normalized_mode = (mode or "").lower()
    issues: list[H3ValidationIssue] = []

    if not 4.0 <= float(duration_sec) <= 15.0:
        _issue(
            issues,
            "duration_range",
            "MiniMax H3 duration must be between 4 and 15 seconds.",
        )

    first_line = text.splitlines()[0].strip() if text else ""
    if normalized_mode == "i2va":
        if first_line != I2VA_ALIGNMENT:
            _issue(issues, "alignment", "I2VA must start with the exact first-frame alignment instruction.")
    elif normalized_mode == "t2va":
        if first_line == I2VA_ALIGNMENT or "fully referenced" in first_line:
            _issue(issues, "alignment", "T2VA must not contain a keyframe alignment instruction.")
    else:
        _issue(issues, "mode", f"Unsupported phase-one H3 mode: {mode}")

    field_headers = re.findall(
        r"(?m)^(integrated_multimodal_description|overall_soundscape|non_diegetic_music):",
        text,
    )
    if field_headers != _FIELDS:
        _issue(
            issues,
            "field_order",
            "H3 fields must appear exactly once in integrated, soundscape, music order.",
        )

    body_match = re.search(
        r"(?ms)^integrated_multimodal_description:\s*(.*?)\n\s*overall_soundscape:",
        text,
    )
    body = body_match.group(1).strip() if body_match else ""
    if not body:
        _issue(issues, "description_missing", "integrated_multimodal_description is empty or malformed.")

    shot_numbers = [int(value) for value in re.findall(r"\[Shot\s+(\d+)\]", body)]
    if not shot_numbers or shot_numbers[0] != 1:
        _issue(issues, "shot_sequence", "The description must begin with [Shot 1].")
    elif shot_numbers != list(range(1, len(shot_numbers) + 1)):
        _issue(issues, "shot_sequence", "Shot numbers must be consecutive and appear once in playback order.")

    cut_values = [
        _seconds(m, s, ms)
        for m, s, ms in re.findall(r"At\s+(\d{2}):(\d{2})\.(\d{3})", body)
    ]
    if any(current <= previous for previous, current in zip(cut_values, cut_values[1:])):
        _issue(issues, "cut_order", "Cut timestamps must be strictly increasing.")
    if any(value >= float(duration_sec) for value in cut_values):
        _issue(issues, "cut_after_duration", "A cut timestamp reaches or exceeds the effective duration.")

    picture_ids = {int(value) for value in re.findall(r"<Picture\s+(\d+)>", text)}
    allowed_pictures = {1} if normalized_mode == "i2va" else set()
    if picture_ids - allowed_pictures:
        _issue(
            issues,
            "unresolved_reference",
            "The prompt contains a picture label not available in the selected mode.",
        )

    dialogue_blocks = re.findall(r"<d>\[[^\]]+\]\s*(.*?)</d>", text, flags=re.DOTALL)
    for expected in expected_dialogue or []:
        if expected not in dialogue_blocks:
            _issue(
                issues,
                "dialogue_changed",
                f"Required dialogue was translated, changed, or omitted: {expected}",
            )

    return H3ValidationReport(valid=not issues, issues=issues)
