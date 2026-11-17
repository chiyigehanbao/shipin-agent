from unittest.mock import MagicMock

from app.services.script_expand import ScriptExpandService, ScriptExpandError


def _scene_with_lines(**extra):
    base = {
        "name": "A",
        "location": "街",
        "time": "夜",
        "characters": ["X", "Y"],
        "props": [],
        "description": "d",
        "lines": [
            {"type": "narration", "speaker": "旁白", "text": "夜深了。", "emotion": ""},
            {"type": "dialogue", "speaker": "X", "text": "走。", "emotion": "急"},
            {"type": "dialogue", "speaker": "Y", "text": "等等。", "emotion": "慌"},
        ],
    }
    base.update(extra)
    return base


def test_expand_parses_scenes():
    llm = MagicMock()
    import json

    llm.chat.return_value = (json.dumps({"scenes": [_scene_with_lines()]}), "ollama")
    svc = ScriptExpandService(llm=llm)
    scenes = svc.expand(text="创意", style="都市")
    assert len(scenes) == 1
    assert scenes[0]["name"] == "A"
    assert scenes[0]["dialogue_count"] == 2
    assert scenes[0]["narration_count"] == 1
    assert len(scenes[0]["lines"]) == 3


def test_expand_parses_scenes_with_lines():
    llm = MagicMock()
    import json

    llm.chat.return_value = (json.dumps({"scenes": [_scene_with_lines()]}), "ollama")
    svc = ScriptExpandService(llm=llm)
    scenes = svc.expand(text="创意", style="都市")
    assert scenes[0]["lines"][1]["text"] == "走。"
    assert scenes[0]["lines"][0]["id"]


def test_expand_retries_when_lines_missing():
    llm = MagicMock()
    import json

    llm.chat.side_effect = [
        (
            json.dumps(
                {
                    "scenes": [
                        {
                            "name": "A",
                            "location": "街",
                            "time": "夜",
                            "characters": ["X"],
                            "props": [],
                            "description": "d",
                            "dialogue_count": 1,
                        }
                    ]
                }
            ),
            "ollama",
        ),
        (json.dumps({"scenes": [_scene_with_lines(name="B")]}), "ollama"),
    ]
    svc = ScriptExpandService(llm=llm)
    scenes = svc.expand(text="x")
    assert scenes[0]["name"] == "B"
    assert scenes[0]["dialogue_count"] >= 2
    assert llm.chat.call_count == 2


def test_expand_retries_then_ok():
    llm = MagicMock()
    import json

    llm.chat.side_effect = [
        ("not json", "ollama"),
        (json.dumps({"scenes": [_scene_with_lines(name="B")]}), "ollama"),
    ]
    svc = ScriptExpandService(llm=llm)
    scenes = svc.expand(text="x")
    assert scenes[0]["name"] == "B"
    assert llm.chat.call_count == 2


def test_expand_fails_after_retry():
    llm = MagicMock()
    llm.chat.return_value = ("{}", "ollama")
    svc = ScriptExpandService(llm=llm)
    try:
        svc.expand(text="x")
        assert False, "expected error"
    except ScriptExpandError:
        pass
