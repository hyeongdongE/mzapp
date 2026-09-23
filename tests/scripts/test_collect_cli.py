from __future__ import annotations

import subprocess
import sys
from datetime import date

from app.config.settings import get_settings
from app.models.enums import Source
from scripts.collect import build_collectors, parse_date


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
    assert "hacker-news" in result.stdout
    assert "github" in result.stdout


def test_parse_date_accepts_wikimedia_backfill_date() -> None:
    assert parse_date("2026-09-18") == date(2026, 9, 18)


def test_all_collects_only_enabled_intelligence_sources() -> None:
    collectors = build_collectors("all", object(), get_settings(), target_date=None)

    assert {collector.source for collector in collectors} == {
        Source.GEEKNEWS,
        Source.HACKER_NEWS,
        Source.GITHUB_RELEASES,
        Source.OFFICIAL_CLOUDFLARE,
        Source.OFFICIAL_AWS,
    }
