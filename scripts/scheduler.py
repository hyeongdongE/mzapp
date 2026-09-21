from __future__ import annotations

import argparse
import asyncio
import signal
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

from app.services.scheduler import SEOUL, SchedulerActions, configure_scheduler
from scripts.build_entities import build
from scripts.collect import collect
from scripts.evaluate import daily, parse_day, weekly


def completed_week_number(poc_start: date, last_complete_day: date) -> int | None:
    complete_days = (last_complete_day - poc_start).days + 1
    if complete_days < 7:
        return None
    return complete_days // 7


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

    return SchedulerActions(
        google=collect_google,
        wikimedia=collect_wikimedia,
        geeknews=collect_geeknews,
        pipeline=run_pipeline,
        daily_evaluation=run_daily_evaluation,
        weekly_evaluation=run_weekly_evaluation,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the single-process trend PoC scheduler")
    parser.add_argument("--poc-start", required=True, type=parse_day)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()
    scheduler = BlockingScheduler(timezone=SEOUL)
    configure_scheduler(scheduler, scheduled_actions(args.poc_start, args.output_dir))

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
