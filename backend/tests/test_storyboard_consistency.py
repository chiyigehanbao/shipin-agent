from app.services.storyboard_consistency import check_storyboard_consistency


def test_flags_conflicting_characters_in_same_scene():
    frames = [
        {
            "id": "f1",
            "number": 1,
            "scene_id": "s1",
            "character": "林澈",
            "description": "入场",
            "prompt_en": "a",
        },
        {
            "id": "f2",
            "number": 2,
            "scene_id": "s1",
            "character": "苏晚",
            "description": "对话",
            "prompt_en": "b",
        },
    ]
    issues = check_storyboard_consistency(frames)
    assert any(i["frame_id"] == "f2" and "不一致" in i["issue"] for i in issues)


def test_empty_when_characters_align():
    frames = [
        {"id": "f1", "number": 1, "scene_id": "s1", "character": "林澈", "prompt_en": "a", "description": "x"},
        {"id": "f2", "number": 2, "scene_id": "s1", "character": "林澈", "prompt_en": "b", "description": "y"},
    ]
    assert check_storyboard_consistency(frames) == []


def test_info_when_missing_english_prompt():
    frames = [
        {
            "id": "f1",
            "number": 1,
            "scene_id": "s1",
            "character": "",
            "description": "雨夜码头",
            "prompt_en": "",
            "description_en": "",
            "image_url": None,
        }
    ]
    issues = check_storyboard_consistency(frames)
    assert len(issues) == 1
    assert issues[0]["severity"] == "info"
