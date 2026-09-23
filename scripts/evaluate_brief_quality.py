from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path

from app.db import session_scope
from app.evaluation.brief_quality_database import load_brief_quality_facts
from app.evaluation.brief_quality_metrics import aggregate_brief_quality
from app.evaluation.brief_quality_reports import (
    render_brief_quality_json,
    render_brief_quality_markdown,
    write_report_pair_atomic,
)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Daily Brief quality reports")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--start-date", type=parse_date, required=True)
    parser.add_argument("--end-date", type=parse_date, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        raise argparse.ArgumentTypeError("start date must not be after end date")
    return args


def report_paths(output_dir: Path, start_date: date, end_date: date) -> tuple[Path, Path]:
    stem = f"brief-quality-{start_date.isoformat()}-{end_date.isoformat()}"
    return output_dir / f"{stem}.json", output_dir / f"{stem}.md"


def generate_reports(
    *, reviewer: str, start_date: date, end_date: date, output_dir: Path
) -> tuple[Path, Path]:
    with session_scope() as session:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        facts = load_brief_quality_facts(
            session, reviewer=reviewer, start_date=start_date, end_date=end_date
        )
        report = aggregate_brief_quality(facts, generated_at=datetime.now(UTC))
    json_path, markdown_path = report_paths(output_dir, start_date, end_date)
    write_report_pair_atomic(
        json_path,
        markdown_path,
        render_brief_quality_json(report),
        render_brief_quality_markdown(report),
    )
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    json_path, markdown_path = generate_reports(
        reviewer=args.reviewer,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir,
    )
    print(json_path)
    print(markdown_path)


if __name__ == "__main__":
    main()
