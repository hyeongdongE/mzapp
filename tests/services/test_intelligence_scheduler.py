from __future__ import annotations

from collections import Counter

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.intelligence_scheduler import (
    IntelligenceSchedulerActions,
    configure_intelligence_scheduler,
)


def test_intelligence_scheduler_registers_stable_seoul_jobs() -> None:
    calls: Counter[str] = Counter()
    actions = IntelligenceSchedulerActions(
        collect=lambda: calls.update(["collect"]),
        process=lambda: calls.update(["process"]),
        generate=lambda: calls.update(["generate"]),
        publish=lambda: calls.update(["publish"]),
    )
    scheduler = BackgroundScheduler()

    configure_intelligence_scheduler(scheduler, actions)
    configure_intelligence_scheduler(scheduler, actions)

    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {
        "intelligence-collect-15m",
        "intelligence-process-15m",
        "intelligence-generate-0730",
        "intelligence-publish-0800",
    }
    assert all(job.coalesce is True for job in jobs.values())
    assert all(job.max_instances == 1 for job in jobs.values())
    assert all(str(job.trigger.timezone) == "Asia/Seoul" for job in jobs.values())
