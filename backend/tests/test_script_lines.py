# backend/tests/test_script_lines.py
from app.services.script_lines import normalize_lines, counts_from_lines


def test_normalize_fills_id_and_counts():
    lines = normalize_lines(
        [
            {"type": "dialogue", "speaker": "甲", "text": "你好", "emotion": "平静"},
            {"type": "narration", "text": "夜深了"},
            {"type": "dialogue", "speaker": "", "text": ""},  # drop empty
        ]
    )
    assert len(lines) == 2
    assert lines[0]["id"].startswith("line_")
    assert lines[0]["speaker"] == "甲"
    assert lines[1]["type"] == "narration"
    d, n = counts_from_lines(lines)
    assert d == 1 and n == 1


def test_normalize_keeps_stable_id():
    lines = normalize_lines(
        [{"id": "line_keep", "type": "dialogue", "speaker": "A", "text": "x"}]
    )
    assert lines[0]["id"] == "line_keep"
