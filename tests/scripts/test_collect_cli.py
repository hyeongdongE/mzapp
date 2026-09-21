from __future__ import annotations

import subprocess
import sys
from datetime import date

from scripts.collect import parse_date


def test_collect_script_can_be_executed_directly() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/collect.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Collect official trend signals" in result.stdout
    assert "geeknews" in result.stdout


def test_parse_date_accepts_wikimedia_backfill_date() -> None:
    assert parse_date("2026-09-18") == date(2026, 9, 18)
