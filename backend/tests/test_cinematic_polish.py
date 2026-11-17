import json
from unittest.mock import MagicMock
from app.services.cinematic_polish import CinematicPolishService, PolishError


def test_parse_and_validate_ok(tmp_path):
    pack = tmp_path / "system.md"
    pack.write_text("sys", encoding="utf-8")
    llm = MagicMock()
    payload = {
        "interpretation_cn": "理解",
        "prompt_en": "a quiet frame",
        "avoid": "hdr look, plastic skin",
        "prompt_cn": "安静画面",
    }
    llm.chat.return_value = (json.dumps(payload), "ollama")
    svc = CinematicPolishService(pack_path=pack, llm=llm)
    out = svc.polish(
        stage="asset",
        text_cn="旧卫衣程序员",
        text_en="",
        context={},
        return_interpretation=True,
    )
    assert out["prompt_en"] == "a quiet frame"
    assert out["provider"] == "ollama"
    assert out["pack_version"] == "cinematic-v1"


def test_missing_prompt_en_retries_then_errors(tmp_path):
    pack = tmp_path / "system.md"
    pack.write_text("sys", encoding="utf-8")
    llm = MagicMock()
    llm.chat.return_value = (json.dumps({"avoid": "x"}), "ollama")
    svc = CinematicPolishService(pack_path=pack, llm=llm)
    try:
        svc.polish(stage="asset", text_cn="a", text_en="", context={})
        assert False
    except PolishError:
        pass
    assert llm.chat.call_count == 2


def test_character_lock_stage_uses_character_pack():
    llm = MagicMock()
    llm.chat.return_value = (
        json.dumps(
            {
                "lock_en": "A woman, 40s, tired eyes, bun, navy coat.",
                "prompt_en": (
                    "A woman, 40s, tired eyes, bun, navy coat. "
                    "Chest-up at a clinic window, daylight from camera-left, "
                    "wool coat texture visible, 50mm, natural exposure."
                ),
                "avoid": "extra limbs, text",
                "prompt_cn": "定妆",
            }
        ),
        "ollama",
    )
    svc = CinematicPolishService(llm=llm)
    out = svc.polish(stage="character_lock", text_cn="女医生", text_en="", context={})
    assert out["lock_en"].startswith("A woman")
    assert out["pack_version"] == "character-lock-v1"
    system = llm.chat.call_args[0][0][0]["content"]
    assert "Character Lock" in system
    assert "Never invent nicknames" in system
    assert "live-action" in system.lower()
    assert "Chen Mo" in system
    assert "clear face" in system.lower() or "短剧" in system or "胸像" in system


def test_character_lock_strips_leaked_instructions():
    llm = MagicMock()
    llm.chat.return_value = (
        json.dumps(
            {
                "lock_en": "Su Yao, late 20s, midnight hair, clear eyes, not a poster climax.",
                "prompt_en": (
                    "Su Yao, late 20s, midnight hair, clear eyes, plain or simple location. "
                    "Waist-up on a wet rooftop, moonlight from camera-left, "
                    "50mm, cotton shirt catching wind, skin texture holding."
                ),
                "avoid": "plastic skin",
                "prompt_cn": "苏遥定妆",
            }
        ),
        "ollama",
    )
    svc = CinematicPolishService(llm=llm)
    out = svc.polish(
        stage="character_lock",
        text_cn="苏遥",
        text_en="",
        context={"name": "苏遥"},
    )
    assert "poster climax" not in out["lock_en"].lower()
    assert "plain or simple" not in out["prompt_en"].lower()
    assert "Su Yao" in out["lock_en"]
    assert "wet rooftop" in out["prompt_en"]


def test_character_lock_rewrites_truncated_nickname():
    llm = MagicMock()
    llm.chat.return_value = (
        json.dumps(
            {
                "lock_en": (
                    "Soo Y (苏遥), a woman in her late 20s, pale skin, "
                    "long loose midnight hair, moon-white irises, a worn black shirt."
                ),
                "prompt_en": (
                    "Soo Y (苏遥), a woman in her late 20s, pale skin, "
                    "long loose midnight hair, moon-white irises, a worn black shirt. "
                    "Chest-up on a wet rooftop, moonlight from camera-left, "
                    "50mm, cotton shirt catching wind, skin texture holding."
                ),
                "avoid": "anime, illustration",
                "prompt_cn": "Soo Y（苏遥），二十多岁，月白虹膜。",
            }
        ),
        "ollama",
    )
    svc = CinematicPolishService(llm=llm)
    out = svc.polish(
        stage="character_lock",
        text_cn="苏遥",
        text_en="",
        context={"name": "苏遥"},
    )
    assert "Soo Y" not in out["lock_en"]
    assert "Soo Y" not in out["prompt_en"]
    assert "苏遥" in out["lock_en"]
    assert out["lock_en"].startswith("苏遥")
    assert "Soo Y" not in out["prompt_cn"]
    assert "苏遥" in out["prompt_cn"]


def test_i2v_motion_accepts_motion_without_prompt_en():
    llm = MagicMock()
    llm.chat.return_value = (
        json.dumps(
            {
                "motion_prompt_en": (
                    "He turns toward the door. Slow push-in. About 5s. "
                    "Keep identity unchanged from the first frame."
                ),
                "avoid": "identity drift",
            }
        ),
        "ollama",
    )
    svc = CinematicPolishService(llm=llm)
    out = svc.polish(stage="i2v_motion", text_cn="转身", text_en="", context={})
    assert out["motion_prompt_en"].startswith("He turns")
    assert out["pack_version"] == "i2v-motion-v1"
    assert out["prompt_en"] == ""

