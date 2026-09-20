from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime

from scripts.replay import parse_boundary


def test_replay_script_can_be_executed_directly() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/replay.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Replay stored official trend observations" in result.stdout


def test_replay_date_boundaries_cover_the_complete_utc_day() -> None:
    assert parse_boundary("2026-09-20", end=False) == datetime(2026, 9, 20, tzinfo=UTC)
    assert parse_boundary("2026-09-20", end=True) == datetime(
        2026, 9, 20, 23, 59, 59, 999999, tzinfo=UTC
    )
