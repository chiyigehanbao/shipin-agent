from app.services.asset_script_sync import collect_candidates, sync_from_script
from app.services.asset_store import AssetStore


def test_collect_characters_and_scenes():
    scenes = [
        {
            "number": 1,
            "name": "开场",
            "location": "竹林",
            "characters": ["张三", "李四", ""],
            "description": "晨雾中对峙",
            "description_en": "standoff in mist",
        },
        {
            "number": 2,
            "name": "客栈",
            "location": "客栈",
            "characters": ["张三", "神秘人"],
            "description": "酒桌上试探",
            "description_en": "",
        },
    ]
    chars, scns = collect_candidates(scenes)
    assert [c["name"] for c in chars] == ["张三", "李四", "神秘人"]
    assert chars[0]["related_descriptions"]
    assert [s["name"] for s in scns] == ["竹林", "客栈"]


def test_sync_creates_pending_and_skips_completed_with_image(tmp_path, monkeypatch):
    from app.services import asset_script_sync as mod

    store = AssetStore(tmp_path / "t.db")
    store.create(
        project_id="p",
        name="张三",
        type="character",
        prompt_cn="old",
        prompt_en="old",
        model="flux",
        status="completed",
    )
    a = store.find_by_name_type("p", "character", "张三")
    store.update("p", a["id"], image_url="/media/assets/p/x.png")

    scenes = [
        {
            "number": 1,
            "name": "开场",
            "location": "竹林",
            "characters": ["张三", "李四"],
            "description": "对峙",
            "description_en": "",
        }
    ]
    project = {"id": "p", "style": "古风武侠", "name": "测"}

    def boom(**kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(mod, "_enrich_one", boom)
    result = sync_from_script(
        project=project,
        scenes=scenes,
        store=store,
        types=("character", "scene"),
        enrich=True,
        default_model="flux",
        polish_svc=object(),
    )
    assert result["skipped"] >= 1
    assert result["created"] >= 1
    assert result["enrich_fallback"] is True
    li = store.find_by_name_type("p", "character", "李四")
    assert li["status"] == "pending"
    assert "古风武侠" in (li["prompt_cn"] + li["prompt_en"])


def test_sync_enrich_uses_character_lock_and_stores_lock_en(tmp_path):
    store = AssetStore(tmp_path / "t.db")

    class FakePolish:
        def polish(self, **kwargs):
            assert kwargs["stage"] == "character_lock"
            return {
                "lock_en": "LOCK ZS",
                "prompt_en": "LOCK ZS standing portrait",
                "prompt_cn": "张三",
                "avoid": "blurry",
            }

    sync_from_script(
        project={"id": "p", "style": "古风"},
        scenes=[
            {
                "name": "开场",
                "location": "竹林",
                "characters": ["张三"],
                "description": "对峙",
            }
        ],
        store=store,
        types=("character",),
        enrich=True,
        polish_svc=FakePolish(),
    )
    item = store.find_by_name_type("p", "character", "张三")
    assert item["lock_en"] == "LOCK ZS"
    assert "LOCK ZS" in item["prompt_en"]


def test_sync_update_resets_model_to_default(tmp_path):
    from app.services import asset_script_sync as mod

    store = AssetStore(tmp_path / "t.db")
    store.create(
        project_id="p",
        name="张三",
        type="character",
        prompt_cn="old",
        prompt_en="old",
        model="sdxl",
        status="pending",
    )

    class FakePolish:
        def polish(self, **kwargs):
            return {
                "lock_en": "LOCK",
                "prompt_en": "LOCK",
                "prompt_cn": "新",
                "avoid": "",
            }

    sync_from_script(
        project={"id": "p", "style": "古风"},
        scenes=[
            {
                "name": "开场",
                "location": "竹林",
                "characters": ["张三"],
                "description": "对峙",
            }
        ],
        store=store,
        types=("character",),
        enrich=True,
        default_model="flux",
        polish_svc=FakePolish(),
    )
    item = store.find_by_name_type("p", "character", "张三")
    assert item["model"] == "flux"
    assert item["status"] == "pending"

