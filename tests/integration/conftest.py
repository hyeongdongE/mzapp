from __future__ import annotations

import os

import pytest
from alembic.config import Config

from alembic import command
from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def isolate_migration_database(request: pytest.FixtureRequest) -> None:
    if not request.path.name.startswith("test_migration_"):
        return
    database_url = os.getenv("TEST_MIGRATION_DATABASE_URL")
    if database_url is None:
        return
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    command.downgrade(Config("alembic.ini"), "base")
