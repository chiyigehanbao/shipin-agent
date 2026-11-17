from app.services.script_suggest import ScriptSuggestService, _has_cue_line, _rule_suggestions


def test_rule_suggests_villain_label_when_only_label_present():
    scenes = [
        {
            "name": "对峙",
            "location": "废弃工厂",
            "characters": ["苏晚", "幕后黑手"],
            "description": "苏晚站在阴影中，听幕后黑手传来冷笑",
            "lines": [
                {"type": "dialogue", "speaker": "幕后黑手", "text": "你逃不掉的。"}
            ],
        }
    ]
    assert any("反派" in s["issue"] for s in _rule_suggestions(scenes))


def test_rule_suggests_silent_scene():
    scenes = [
        {
            "name": "雨夜",
            "location": "巷口",
            "characters": ["苏晚"],
            "description": "雨很大，她站着不动。",
            "lines": [],
        }
    ]
    svc = ScriptSuggestService(llm=None)
    out = svc.suggest(scenes)
    assert any("没有对白" in s["issue"] for s in out)


def test_rule_suggests_thin_scene_prompt():
    scenes = [
        {
            "name": "车站",
            "location": "废弃车站",
            "characters": ["苏晚"],
            "description": "她走进车站",
            "lines": [{"type": "narration", "text": "灯光忽明忽灭。"}],
        }
    ]
    out = ScriptSuggestService(llm=None).suggest(scenes)
    assert any("场面描写过短" in s["issue"] for s in out)


def test_rule_empty_scenes_returns_empty():
    assert ScriptSuggestService(llm=None).suggest([]) == []


def test_cue_detection():
    assert _has_cue_line({"description": "幕后黑手现身"}, ("反派", "幕后黑手"))
    assert not _has_cue_line({"description": "苏晚出手"}, ("反派", "幕后黑手"))