from __future__ import annotations

from datetime import UTC, datetime

import pytest


@pytest.fixture
def intelligence_now() -> datetime:
    return datetime(2026, 9, 23, 0, 0, tzinfo=UTC)
