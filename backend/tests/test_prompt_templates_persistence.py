import tempfile
from pathlib import Path
from unittest.mock import patch

from app.db.repositories.prompt_templates import PromptTemplateRepository
from app.services import prompt_templates as pt


def _repo(tmp_path):
    return PromptTemplateRepository(tmp_path / "pt.db")


def test_repo_create_get_list(tmp_path: Path):
    repo = _repo(tmp_path)
    tpl = repo.create(
        {
            "name": "自定义模板",
            "name_en": "Custom",
            "category": "character",
            "system_prompt_cn": "sys",
            "system_prompt_en": "sys_en",
            "user_prompt_cn": "user",
            "user_prompt_en": "user_en",
        }
    )
    assert tpl["id"]
    got = repo.get(tpl["id"])
    assert got["name"] == "自定义模板"
    assert any(t["id"] == tpl["id"] for t in repo.list_all())


def test_repo_update_persists(tmp_path: Path):
    repo = _repo(tmp_path)
    tpl = repo.create({"name": "旧名", "category": "scene"})
    repo.update(tpl["id"], {"name": "新名"})
    assert repo.get(tpl["id"])["name"] == "新名"


def test_repo_delete(tmp_path: Path):
    repo = _repo(tmp_path)
    tpl = repo.create({"name": "待删", "category": "scene"})
    assert repo.delete(tpl["id"]) is True
    assert repo.get(tpl["id"]) is None


def test_get_template_overrides_seed_via_persisted(tmp_path: Path):
    repo = _repo(tmp_path)
    seed = pt.get_template("tpl_001")
    assert seed is not None
    # 覆写种子模板内容
    repo.create({**seed, "id": "tpl_001", "user_prompt_cn": "改写过"})
    with patch.object(
        pt,
        "_persisted_map",
        return_value={"tpl_001": {**seed, "user_prompt_cn": "改写过"}},
    ):
        got = pt.get_template("tpl_001")
        assert got["user_prompt_cn"] == "改写过"


def test_list_includes_new_persisted_template(tmp_path: Path):
    repo = _repo(tmp_path)
    tpl = repo.create({"name": "新模板A", "category": "character"})
    with patch.object(pt, "_persisted_map", return_value={tpl["id"]: tpl}):
        rows = pt.list_templates()
        assert any(t["id"] == tpl["id"] and t["name"] == "新模板A" for t in rows)
