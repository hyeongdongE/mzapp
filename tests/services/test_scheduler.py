from __future__ import annotations

from collections import Counter

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from app.services.scheduler import SchedulerActions, configure_scheduler
from scripts.scheduler import scheduled_actions


def test_scheduler_registers_stable_non_overlapping_jobs_in_seoul_time() -> None:
    calls: Counter[str] = Counter()
    actions = SchedulerActions(
        google=lambda: calls.update(["google"]),
        wikimedia=lambda: calls.update(["wikimedia"]),
        geeknews=lambda: calls.update(["geeknews"]),
        pipeline=lambda: calls.update(["pipeline"]),
        daily_evaluation=lambda: calls.update(["daily"]),
        weekly_evaluation=lambda: calls.update(["weekly"]),
    )
    scheduler = BackgroundScheduler()

    configure_scheduler(scheduler, actions)
    configure_scheduler(scheduler, actions)

    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {
        "collect-google-hourly",
        "collect-wikimedia-daily",
        "collect-geeknews-hourly",
        "pipeline-after-collection",
        "evaluate-daily",
        "evaluate-weekly",
    }
    assert all(job.max_instances == 1 for job in jobs.values())
    assert all(job.coalesce is True for job in jobs.values())
    assert str(jobs["collect-wikimedia-daily"].trigger.timezone) == "Asia/Seoul"
    assert "day_of_week='mon'" in str(jobs["evaluate-weekly"].trigger)


def test_failed_google_job_does_not_suppress_wikimedia_job() -> None:
    calls: Counter[str] = Counter()

    def fail_google() -> None:
        calls.update(["google"])
        raise RuntimeError("google unavailable")

    actions = SchedulerActions(
        google=fail_google,
        wikimedia=lambda: calls.update(["wikimedia"]),
        geeknews=lambda: calls.update(["geeknews"]),
        pipeline=lambda: None,
        daily_evaluation=lambda: None,
        weekly_evaluation=lambda: None,
    )
    scheduler = BackgroundScheduler()
    configure_scheduler(scheduler, actions)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    with pytest.raises(RuntimeError, match="google unavailable"):
        jobs["collect-google-hourly"].func()
    jobs["collect-wikimedia-daily"].func()

    assert calls == Counter({"google": 1, "wikimedia": 1})


def test_production_scheduler_actions_include_intelligence_jobs(tmp_path) -> None:
    actions = scheduled_actions(
        poc_start=__import__("datetime").date(2026, 9, 1),
        output_dir=tmp_path,
    )
    scheduler = BackgroundScheduler()

    configure_scheduler(scheduler, actions)

    assert actions.intelligence is not None
    assert {
        "intelligence-collect-15m",
        "intelligence-process-15m",
        "intelligence-generate-0735",
        "intelligence-publish-0800",
    } <= {job.id for job in scheduler.get_jobs()}
