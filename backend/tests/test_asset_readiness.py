from app.services.asset_readiness import (
    is_character_ready,
    lock_has_face_cue,
    readiness_reasons,
    unready_character_names,
)


def test_ready_requires_lock_image_completed():
    assert is_character_ready(
        {
            "type": "character",
            "lock_en": "A woman, late 20s, clear eyes.",
            "status": "completed",
            "image_url": "/media/x.png",
        }
    )
    assert not is_character_ready(
        {
            "type": "character",
            "lock_en": "A woman",
            "status": "failed",
            "image_url": "/media/x.png",
        }
    )
    assert "missing_image" in readiness_reasons(
        {
            "type": "character",
            "lock_en": "x",
            "status": "completed",
            "image_url": None,
        }
    )


def test_unready_names_from_scene_cast():
    assets = [
        {
            "type": "character",
            "name": "苏遥",
            "lock_en": "L",
            "status": "completed",
            "image_url": "/a.png",
        },
        {
            "type": "character",
            "name": "黑衣人",
            "lock_en": "",
            "status": "pending",
            "image_url": None,
        },
    ]
    assert unready_character_names(assets, ["苏遥", "黑衣人", "路人"]) == [
        "黑衣人",
        "路人",
    ]


def test_lock_has_face_cue():
    assert lock_has_face_cue("late 20s, moon-white irises, pale skin")
    assert not lock_has_face_cue("a person in a coat")


def test_unselected_casting_candidates_are_not_ready():
    base = {
        "type": "character",
        "lock_en": "clear almond eyes and a soft oval face",
        "status": "completed",
        "image_url": "/media/candidate.png",
    }
    assert not is_character_ready({**base, "selection_status": "candidate"})
    assert not is_character_ready({**base, "selection_status": "rejected"})
    assert "not_selected" in readiness_reasons(
        {**base, "selection_status": "candidate"}
    )
    assert is_character_ready({**base, "selection_status": "selected"})


def test_unready_names_prefers_selected_take_over_newer_candidates():
    assets = [
        {
            "id": "candidate",
            "type": "character",
            "name": "苏遥",
            "lock_en": "anchor B",
            "status": "completed",
            "image_url": "/b.png",
            "selection_status": "candidate",
        },
        {
            "id": "selected",
            "type": "character",
            "name": "苏遥",
            "lock_en": "anchor A",
            "status": "completed",
            "image_url": "/a.png",
            "selection_status": "selected",
        },
    ]
    assert unready_character_names(assets, ["苏遥"]) == []
