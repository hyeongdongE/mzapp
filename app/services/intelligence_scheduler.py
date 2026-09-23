from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.collectors.base import Collector, CollectorError
from app.intelligence.assessment import AssessmentService
from app.intelligence.facts import FactBuilder
from app.models.enums import Source
from app.services.daily_brief import DailyBriefResult, DailyBriefService
from app.services.event_processing import EventProcessingResult, EventProcessingService
from app.services.intelligence_collection import IntelligenceCollectionService

SEOUL = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class IntelligenceSchedulerActions:
    collect: Callable[[], None]
    process: Callable[[], None]
    generate: Callable[[], None]
    publish: Callable[[], None]


def configure_intelligence_scheduler(
    scheduler: BaseScheduler,
    actions: IntelligenceSchedulerActions,
) -> BaseScheduler:
    common = {"replace_existing": True, "coalesce": True, "max_instances": 1}
    scheduler.add_job(
        actions.collect,
        CronTrigger(minute="*/15", timezone=SEOUL),
        id="intelligence-collect-15m",
        **common,
    )
    scheduler.add_job(
        actions.process,
        CronTrigger(minute="2,17,32,47", timezone=SEOUL),
        id="intelligence-process-15m",
        **common,
    )
    scheduler.add_job(
        actions.generate,
        CronTrigger(hour=7, minute=35, timezone=SEOUL),
        id="intelligence-generate-0735",
        **common,
    )
    scheduler.add_job(
        actions.publish,
        CronTrigger(hour=8, minute=0, timezone=SEOUL),
        id="intelligence-publish-0800",
        **common,
    )
    return scheduler


@dataclass(frozen=True)
class PipelineCollectionResult:
    source: Source
    succeeded: bool
    run_id: int | None
    raw_item_count: int
    error_code: str | None


class IntelligencePipeline:
    def __init__(
        self,
        session: Session,
        *,
        now: Callable[[], datetime] | None = None,
        github_repositories: tuple[str, ...] | None = None,
    ) -> None:
        self._session = session
        self._now = now or (lambda: datetime.now(UTC))
        self._github_repositories = github_repositories

    async def collect(
        self,
        collectors: list[Collector],
        *,
        as_of: datetime,
    ) -> list[PipelineCollectionResult]:
        results = []
        source_counts: dict[Source, int] = {}
        for collector in collectors:
            index = source_counts.get(collector.source, 0)
            source_counts[collector.source] = index + 1
            collection_key = getattr(collector, "collection_key", None)
            suffix = (
                f":{collection_key}"
                if collection_key
                else (f":{index}" if index else "")
            )
            run_key = (
                f"intelligence:{collector.source.value.lower()}{suffix}:"
                f"{as_of:%Y%m%dT%H%M%SZ}"
            )
            try:
                result = await IntelligenceCollectionService(
                    self._session, now=self._now
                ).run(collector, as_of=as_of, run_key=run_key)
            except CollectorError as exc:
                results.append(
                    PipelineCollectionResult(
                        collector.source,
                        False,
                        None,
                        0,
                        exc.code,
                    )
                )
                continue
            results.append(
                PipelineCollectionResult(
                    collector.source,
                    True,
                    result.run_id,
                    result.inserted_raw_items,
                    None,
                )
            )
        return results

    def process(
        self,
        window_start: datetime,
        window_end: datetime,
        *,
        version: str,
        assessment_version: str,
    ) -> EventProcessingResult:
        result = EventProcessingService(self._session, now=self._now).process_window(
            window_start,
            window_end,
            version=version,
        )
        for event_id in result.cluster_ids:
            FactBuilder(self._session).build(event_id)
            AssessmentService(self._session).assess(
                event_id,
                version=assessment_version,
            )
        return result

    def generate(
        self,
        brief_date: date,
        *,
        now: datetime,
        version: str,
    ) -> DailyBriefResult:
        return DailyBriefService(
            self._session,
            github_repositories=self._github_repositories,
        ).generate(
            brief_date,
            now=now,
            version=version,
        )

    def publish(
        self,
        brief_date: date,
        *,
        now: datetime,
        recovery_version: str | None = None,
    ) -> DailyBriefResult:
        return DailyBriefService(
            self._session,
            github_repositories=self._github_repositories,
        ).publish(brief_date, now=now, recovery_version=recovery_version)
