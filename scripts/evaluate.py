from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.db import session_scope
from app.evaluation.database import evaluate_day
from app.evaluation.reports import (
    aggregate_week,
    render_daily_markdown,
    render_weekly_markdown,
    write_report_atomic,
)


def parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def daily(day: date, output_dir: Path) -> Path:
    with session_scope() as session:
        result = evaluate_day(session, day)
    target = output_dir / f"{day.isoformat()}.md"
    write_report_atomic(target, render_daily_markdown(result))
    return target


def weekly(week_number: int, poc_start: date, output_dir: Path) -> Path:
    if week_number < 1:
        raise ValueError("week must be at least 1")
    start = poc_start + timedelta(days=(week_number - 1) * 7)
    with session_scope() as session:
        days = [
            evaluate_day(session, start + timedelta(days=offset))
            for offset in range(7)
        ]
    result = aggregate_week(days, week_number=week_number)
    target = output_dir / f"week-{week_number:02d}.md"
    write_report_atomic(target, render_weekly_markdown(result))
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic trend evaluation reports"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    daily_parser = subparsers.add_parser("daily")
    daily_parser.add_argument("--date", type=parse_day, default=datetime.now(UTC).date())
    weekly_parser = subparsers.add_parser("weekly")
    weekly_parser.add_argument("--week", type=int, required=True)
    weekly_parser.add_argument("--poc-start", type=parse_day, required=True)
    args = parser.parse_args()
    if args.command == "daily":
        path = daily(args.date, args.output_dir)
    else:
        path = weekly(args.week, args.poc_start, args.output_dir)
    print(path)


if __name__ == "__main__":
    main()
