from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.collectors.base import Collector, CollectorError
from app.models.enums import Source
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
        CronTrigger(hour=7, minute=30, timezone=SEOUL),
        id="intelligence-generate-0730",
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
    ) -> None:
        self._session = session
        self._now = now or (lambda: datetime.now(UTC))

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
            suffix = f":{index}" if index else ""
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
