from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.intelligence_scheduler import (
    IntelligenceSchedulerActions,
    configure_intelligence_scheduler,
)

SEOUL = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class SchedulerActions:
    google: Callable[[], None]
    wikimedia: Callable[[], None]
    geeknews: Callable[[], None]
    pipeline: Callable[[], None]
    daily_evaluation: Callable[[], None]
    weekly_evaluation: Callable[[], None]
    intelligence: IntelligenceSchedulerActions | None = None


def configure_scheduler(
    scheduler: BaseScheduler, actions: SchedulerActions
) -> BaseScheduler:
    common = {"replace_existing": True, "coalesce": True, "max_instances": 1}
    scheduler.add_job(
        actions.google,
        CronTrigger(minute=0, timezone=SEOUL),
        id="collect-google-hourly",
        **common,
    )
    scheduler.add_job(
        actions.wikimedia,
        CronTrigger(hour=9, minute=5, timezone=SEOUL),
        id="collect-wikimedia-daily",
        **common,
    )
    scheduler.add_job(
        actions.geeknews,
        CronTrigger(minute=5, timezone=SEOUL),
        id="collect-geeknews-hourly",
        **common,
    )
    scheduler.add_job(
        actions.pipeline,
        CronTrigger(minute=10, timezone=SEOUL),
        id="pipeline-after-collection",
        **common,
    )
    scheduler.add_job(
        actions.daily_evaluation,
        CronTrigger(hour=9, minute=30, timezone=SEOUL),
        id="evaluate-daily",
        **common,
    )
    scheduler.add_job(
        actions.weekly_evaluation,
        CronTrigger(day_of_week="mon", hour=10, minute=0, timezone=SEOUL),
        id="evaluate-weekly",
        **common,
    )
    if actions.intelligence is not None:
        configure_intelligence_scheduler(scheduler, actions.intelligence)
    return scheduler
