from __future__ import annotations

import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import scripts.scheduler as scheduler_script
from scripts.scheduler import completed_week_number


def test_scheduler_script_can_be_executed_directly() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/scheduler.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "single-process trend PoC scheduler" in result.stdout


def test_completed_week_number_does_not_skip_week_one() -> None:
    poc_start = date(2026, 9, 20)

    assert completed_week_number(poc_start, date(2026, 9, 25)) is None
    assert completed_week_number(poc_start, date(2026, 9, 26)) == 1
    assert completed_week_number(poc_start, date(2026, 9, 27)) == 1
    assert completed_week_number(poc_start, date(2026, 10, 3)) == 2


def test_daily_job_refreshes_delayed_wikimedia_source_day(monkeypatch) -> None:
    days: list[date] = []
    monkeypatch.setattr(scheduler_script, "daily", lambda day, _output_dir: days.append(day))
    actions = scheduler_script.scheduled_actions(
        date(2026, 9, 20),
        Path("reports"),
        now=lambda: datetime(2026, 9, 23, 0, 30, tzinfo=UTC),
    )

    actions.daily_evaluation()

    assert days == [date(2026, 9, 22), date(2026, 9, 21)]
