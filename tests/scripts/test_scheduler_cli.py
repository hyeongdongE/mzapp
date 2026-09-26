from __future__ import annotations

import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

import scripts.scheduler as scheduler_script
from scripts.scheduler import completed_week_number, configure_scheduler_mode


def test_scheduler_script_can_be_executed_directly() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/scheduler.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "single-process trend PoC scheduler" in result.stdout
    assert "intelligence-only" in result.stdout


def test_production_mode_registers_only_intelligence_jobs(tmp_path: Path) -> None:
    scheduler = BackgroundScheduler()
    actions = scheduler_script.scheduled_actions(date(2026, 9, 20), tmp_path)

    configure_scheduler_mode(scheduler, actions, "intelligence-only")

    assert {job.id for job in scheduler.get_jobs()} == {
        "intelligence-collect-15m",
        "intelligence-process-15m",
        "intelligence-generate-0735",
        "intelligence-publish-0800",
    }


def test_production_mode_never_runs_legacy_collectors_or_evaluations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sources: list[str] = []

    async def record(source: str, _as_of: datetime, *, target_date=None) -> list:
        del target_date
        sources.append(source)
        return []

    monkeypatch.setattr(scheduler_script, "collect", record)
    scheduler = BackgroundScheduler()
    actions = scheduler_script.scheduled_actions(date(2026, 9, 20), tmp_path)
    configure_scheduler_mode(scheduler, actions, "intelligence-only")
    jobs = {job.id: job for job in scheduler.get_jobs()}

    jobs["intelligence-collect-15m"].func()

    assert sources == ["all"]
    assert not {"collect-google-hourly", "collect-wikimedia-daily", "evaluate-daily"} & jobs.keys()


def test_default_combined_mode_preserves_existing_jobs(tmp_path: Path) -> None:
    scheduler = BackgroundScheduler()
    actions = scheduler_script.scheduled_actions(date(2026, 9, 20), tmp_path)

    configure_scheduler_mode(scheduler, actions, "combined")

    assert {job.id for job in scheduler.get_jobs()} == {
        "collect-google-hourly",
        "collect-wikimedia-daily",
        "collect-geeknews-hourly",
        "pipeline-after-collection",
        "evaluate-daily",
        "evaluate-weekly",
        "intelligence-collect-15m",
        "intelligence-process-15m",
        "intelligence-generate-0735",
        "intelligence-publish-0800",
    }


def test_unknown_scheduler_mode_fails_closed(tmp_path: Path) -> None:
    actions = scheduler_script.scheduled_actions(date(2026, 9, 20), tmp_path)

    with pytest.raises(ValueError, match="unsupported scheduler mode"):
        configure_scheduler_mode(BackgroundScheduler(), actions, "unknown")


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


def test_geeknews_job_uses_the_official_collector_path(monkeypatch) -> None:
    sources: list[str] = []

    async def record(source: str, _as_of: datetime, *, target_date=None) -> list:
        del target_date
        sources.append(source)
        return []

    monkeypatch.setattr(scheduler_script, "collect", record)
    actions = scheduler_script.scheduled_actions(
        date(2026, 9, 20),
        Path("reports"),
        now=lambda: datetime(2026, 9, 21, 5, 0, tzinfo=UTC),
    )

    actions.geeknews()

    assert sources == ["geeknews"]
