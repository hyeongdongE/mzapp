from __future__ import annotations

import argparse
import asyncio
import signal
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from app.db import session_scope
from app.services.intelligence_scheduler import (
    IntelligencePipeline,
    IntelligenceSchedulerActions,
    configure_intelligence_scheduler,
)
from app.services.scheduler import SEOUL, SchedulerActions, configure_scheduler
from scripts.build_entities import build
from scripts.collect import collect
from scripts.evaluate import daily, parse_day, weekly


def completed_week_number(poc_start: date, last_complete_day: date) -> int | None:
    complete_days = (last_complete_day - poc_start).days + 1
    if complete_days < 7:
        return None
    return complete_days // 7


def configure_scheduler_mode(
    scheduler: BaseScheduler,
    actions: SchedulerActions,
    mode: str,
) -> BaseScheduler:
    if mode == "intelligence-only":
        if actions.intelligence is None:
            raise ValueError("intelligence-only mode requires intelligence actions")
        return configure_intelligence_scheduler(scheduler, actions.intelligence)
    if mode == "combined":
        return configure_scheduler(scheduler, actions)
    raise ValueError(f"unsupported scheduler mode: {mode}")


def scheduled_actions(
    poc_start: date,
    output_dir: Path,
    *,
    now: Callable[[], datetime] | None = None,
) -> SchedulerActions:
    clock = now or (lambda: datetime.now(UTC))

    def collect_google() -> None:
        current = clock()
        asyncio.run(collect("google", current))

    def collect_wikimedia() -> None:
        current = clock()
        target_date = (current - timedelta(days=2)).date()
        asyncio.run(collect("wikimedia", current, target_date=target_date))

    def collect_geeknews() -> None:
        current = clock()
        asyncio.run(collect("geeknews", current))

    def run_pipeline() -> None:
        asyncio.run(build(None, None, None))

    def run_daily_evaluation() -> None:
        current_day = clock().date()
        daily(current_day - timedelta(days=1), output_dir)
        # Wikimedia D-2 arrives after the original report, so refresh that source-day diagnostic.
        daily(current_day - timedelta(days=2), output_dir)

    def run_weekly_evaluation() -> None:
        last_complete_day = clock().date() - timedelta(days=1)
        week_number = completed_week_number(poc_start, last_complete_day)
        if week_number is None:
            return
        weekly(week_number, poc_start, output_dir)

    def collect_intelligence() -> None:
        asyncio.run(collect("all", clock()))

    def process_intelligence() -> None:
        current = clock()
        with session_scope() as session:
            IntelligencePipeline(session, now=clock).process(
                current - timedelta(days=2),
                current,
                version="cluster-v1",
                assessment_version="assessment-v1",
            )

    def generate_intelligence() -> None:
        current = clock()
        brief_date = current.astimezone(SEOUL).date()
        with session_scope() as session:
            IntelligencePipeline(session, now=clock).generate(
                brief_date,
                now=current,
                version="brief-v1",
            )

    def publish_intelligence() -> None:
        current = clock()
        brief_date = current.astimezone(SEOUL).date()
        with session_scope() as session:
            IntelligencePipeline(session, now=clock).publish(
                brief_date,
                now=current,
                recovery_version="brief-v1-publish",
            )

    return SchedulerActions(
        google=collect_google,
        wikimedia=collect_wikimedia,
        geeknews=collect_geeknews,
        pipeline=run_pipeline,
        daily_evaluation=run_daily_evaluation,
        weekly_evaluation=run_weekly_evaluation,
        intelligence=IntelligenceSchedulerActions(
            collect=collect_intelligence,
            process=process_intelligence,
            generate=generate_intelligence,
            publish=publish_intelligence,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the single-process trend PoC scheduler")
    parser.add_argument("--poc-start", required=True, type=parse_day)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    parser.add_argument("--mode", choices=("combined", "intelligence-only"), default="combined")
    args = parser.parse_args()
    scheduler = BlockingScheduler(timezone=SEOUL)
    configure_scheduler_mode(
        scheduler, scheduled_actions(args.poc_start, args.output_dir), args.mode
    )

    def stop_scheduler(_signum: int, _frame: object) -> None:
        raise SystemExit

    signal.signal(signal.SIGTERM, stop_scheduler)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        if scheduler.running:
            scheduler.shutdown(wait=True)


if __name__ == "__main__":
    main()
