import pytest

from app.services.h3_validator import I2VA_ALIGNMENT, validate_h3_prompt


VALID_T2VA = """integrated_multimodal_description: [Shot 1] Live-action, cinematic, a woman waits beside a rain-covered window. The camera holds a static shot while she says: <d>[Chinese] 别回头。</d> [Shot 2] At 00:03.500, the camera cuts to a close-up of her hand closing around the letter.

overall_soundscape: Rain ticks against the glass while paper rustles softly.

non_diegetic_music: Sparse piano notes at a slow tempo."""

VALID_I2VA = f"""{I2VA_ALIGNMENT}

integrated_multimodal_description: [Shot 1] Live-action, cinematic, the woman shown in <Picture 1> preserves her appearance, clothing, position, and the room layout. The camera pushes in with small amplitude at slow speed as she lifts her gaze and folds the letter.

overall_soundscape: Rain ticks against the window and paper rustles in her hands.

non_diegetic_music: N/A"""


def issue_codes(report):
    return {issue.code for issue in report.issues}


def test_accepts_valid_t2va_and_preserves_dialogue():
    report = validate_h3_prompt(
        VALID_T2VA,
        mode="t2va",
        duration_sec=5.17,
        expected_dialogue=["别回头。"],
    )
    assert report.valid is True
    assert report.issues == []


def test_accepts_valid_i2va_alignment():
    report = validate_h3_prompt(VALID_I2VA, mode="i2va", duration_sec=5.17)
    assert report.valid is True


@pytest.mark.parametrize(
    ("content", "mode", "duration", "code"),
    [
        (
            VALID_T2VA.replace(
                "integrated_multimodal_description:",
                "overall_soundscape: duplicate\n\nintegrated_multimodal_description:",
                1,
            ),
            "t2va",
            5.17,
            "field_order",
        ),
        (VALID_I2VA.replace("0.00 seconds", "0.50 seconds", 1), "i2va", 5.17, "alignment"),
        (VALID_T2VA.replace("00:03.500", "00:05.500"), "t2va", 5.17, "cut_after_duration"),
        (VALID_T2VA.replace("[Shot 2]", "[Shot 3]"), "t2va", 5.17, "shot_sequence"),
        (VALID_I2VA.replace("<Picture 1>", "<Picture 2>", 1), "i2va", 5.17, "unresolved_reference"),
    ],
)
def test_rejects_structural_errors(content, mode, duration, code):
    report = validate_h3_prompt(content, mode=mode, duration_sec=duration)
    assert report.valid is False
    assert code in issue_codes(report)


def test_rejects_changed_or_missing_dialogue():
    changed = VALID_T2VA.replace("别回头。", "快走。")
    report = validate_h3_prompt(
        changed,
        mode="t2va",
        duration_sec=5.17,
        expected_dialogue=["别回头。"],
    )
    assert "dialogue_changed" in issue_codes(report)


def test_rejects_duration_outside_h3_range():
    report = validate_h3_prompt(VALID_T2VA, mode="t2va", duration_sec=2.0)
    assert "duration_range" in issue_codes(report)
