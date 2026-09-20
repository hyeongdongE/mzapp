from __future__ import annotations

import subprocess
import sys
from datetime import date

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
