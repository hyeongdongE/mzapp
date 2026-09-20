from __future__ import annotations

from collections import Counter

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from app.services.scheduler import SchedulerActions, configure_scheduler


def test_scheduler_registers_stable_non_overlapping_jobs_in_seoul_time() -> None:
    calls: Counter[str] = Counter()
    actions = SchedulerActions(
        google=lambda: calls.update(["google"]),
        wikimedia=lambda: calls.update(["wikimedia"]),
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
