from pathlib import Path

from app.core.settings import settings


def test_test_runtime_never_uses_production_database():
    production = Path(__file__).resolve().parents[1] / "data" / "shipin-agent.db"
    assert settings.resolved_sqlite_path.resolve() != production.resolve()
    assert "pytest" in settings.resolved_sqlite_path.name


def test_storyboard_render_runtime_uses_test_database():
    from app.services.runtime import render_attempt_repo, render_request_repo

    assert render_attempt_repo.db_path is None
    assert render_request_repo.db_path is None
    assert "pytest" in settings.resolved_sqlite_path.name
