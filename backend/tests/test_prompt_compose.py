from app.services.prompt_compose import (
    collect_lock_ens,
    compose_still_prompt,
    resolve_i2v_prompt,
)


def test_compose_prepends_lock_verbatim():
    lock = "A man, 30s, short black hair, grey linen shirt."
    body = "He waits at the rainy cafe window, 50mm, tungsten practical."
    out = compose_still_prompt(body, [lock])
    assert out.startswith(lock)
    assert "rainy cafe window" in out
    assert out.count(lock) == 1


def test_compose_does_not_duplicate_existing_lock():
    lock = "A man, 30s, short black hair, grey linen shirt."
    body = f"{lock}\nHe waits."
    assert compose_still_prompt(body, [lock]) == body


def test_collect_lock_ens_matches_names():
    assets = [
        {"type": "character", "name": "张三", "lock_en": "CHAR LOCK"},
        {"type": "scene", "name": "咖啡馆", "lock_en": "SCENE LOCK"},
        {"type": "character", "name": "李四", "lock_en": ""},
    ]
    locks = collect_lock_ens(assets, character_name="张三", scene_name="咖啡馆")
    assert locks == ["CHAR LOCK", "SCENE LOCK"]


def test_resolve_i2v_prefers_motion():
    frame = {
        "prompt_en": "LOCK TEXT plus a still description with wardrobe",
        "motion_prompt_en": "He turns to the door. Slow push-in. About 5s.",
        "movement": "推进",
        "duration": 5,
        "description_en": "turns",
    }
    assert resolve_i2v_prompt(frame) == frame["motion_prompt_en"]


def test_resolve_i2v_does_not_use_still_prompt_as_fallback():
    frame = {
        "prompt_en": "A man, 30s, short black hair, grey linen shirt. Cafe window still.",
        "motion_prompt_en": "",
        "movement": "固定",
        "duration": 3,
        "description_en": "He lowers the cup.",
        "description": "他放下杯子",
    }
    out = resolve_i2v_prompt(frame)
    assert "short black hair" not in out
    assert "He lowers the cup" in out
    assert "first frame" in out.lower()


def test_character_portrait_split_rejects_identical_lock_and_prompt():
    from app.services.prompt_compose import character_portrait_split_error

    lock = "Su Yao, late 20s, midnight hair."
    assert character_portrait_split_error(lock, lock) == "prompt_en must add staging, not copy lock_en"
    assert character_portrait_split_error(lock, lock + " city haze") == "prompt_en staging too thin"
    ok = character_portrait_split_error(
        lock,
        lock + " Chest-up on a rooftop, moonlight from the left, 50mm, cotton wear visible.",
    )
    assert ok == ""


def test_sanitize_strips_leaked_pack_instructions():
    from app.services.prompt_compose import sanitize_lock_fields

    out = sanitize_lock_fields(
        {
            "lock_en": (
                "Su Yao, late 20s, midnight hair. standing or chest-up, "
                "plain or simple location, not a poster climax."
            ),
            "prompt_en": "Su Yao, late 20s, midnight hair. not a poster climax",
        }
    )
    assert "poster climax" not in out["lock_en"].lower()
    assert "plain or simple" not in out["lock_en"].lower()
    assert "Su Yao" in out["lock_en"]
    assert "poster climax" not in out["prompt_en"].lower()


def test_restore_given_name_keeps_full_pinyin():
    from app.services.prompt_compose import restore_given_name

    out = restore_given_name(
        {
            "lock_en": "Su Yao (苏遥), late 20s, midnight hair.",
            "prompt_en": "Su Yao (苏遥), late 20s, midnight hair. Chest-up on a rooftop.",
            "prompt_cn": "苏遥，二十多岁。",
        },
        "苏遥",
    )
    assert out["lock_en"].startswith("Su Yao (苏遥)")
    assert "Soo Y" not in out["lock_en"]


def test_restore_given_name_strips_truncated_fullwidth_parens():
    from app.services.prompt_compose import restore_given_name

    out = restore_given_name(
        {
            "lock_en": "Soo Y (苏遥), late 20s.",
            "prompt_en": "Soo Y (苏遥), late 20s. Chest-up on a wet rooftop at night.",
            "prompt_cn": "Soo Y（苏遥），二十多岁。",
        },
        "苏遥",
    )
    assert "Soo Y" not in out["lock_en"]
    assert "Soo Y" not in out["prompt_cn"]
    assert out["lock_en"].startswith("苏遥")
    assert "苏遥" in out["prompt_cn"]
