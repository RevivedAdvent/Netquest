"""Pytest fixtures: a fresh, isolated NetQuest app with a temporary database."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-key"
    _tmp = tempfile.mkdtemp(prefix="netquest-test-")
    INSTANCE_DIR = Path(_tmp)
    DATABASE = Path(_tmp) / "test.db"


@pytest.fixture(scope="session")
def app():
    from app import create_app

    application = create_app(TestConfig)
    with application.app_context():
        from database import init_db

        init_db(application)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def fresh_db(app):
    """Empty every progress table between tests."""
    with app.app_context():
        from database import execute

        for table in [
            "module_progress", "lesson_progress", "attempts", "mission_progress",
            "mission_evidence", "lab_progress", "simulation_progress", "activity",
            "interview_answers", "interview_sessions", "user_settings",
        ]:
            execute(f"DELETE FROM {table}")
        yield
