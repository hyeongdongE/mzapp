from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx

from app.collectors.http import SafeHttpClient
from app.config.settings import get_settings
from app.db import session_scope
from app.services.intelligence_scheduler import IntelligencePipeline
from scripts.collect import build_collectors


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    with session_scope() as session:
        pipeline = IntelligencePipeline(session)
        if args.collect:
            async with httpx.AsyncClient() as client:
                safe_http = SafeHttpClient(
                    client,
                    allowed_hosts={
                        "news.hada.io",
                        "hacker-news.firebaseio.com",
                        "api.github.com",
                        "blog.cloudflare.com",
                        "aws.amazon.com",
                    },
                    max_bytes=settings.http_max_bytes,
                    retries=settings.http_retries,
                    timeout_seconds=settings.http_timeout_seconds,
                    user_agent=settings.user_agent,
                )
                collectors = build_collectors(
                    "all", safe_http, settings, target_date=None
                )
                collection = await pipeline.collect(collectors, as_of=now)
                for result in collection:
                    print(
                        f"collect source={result.source.value} "
                        f"status={'ok' if result.succeeded else 'failed'} "
                        f"raw_items={result.raw_item_count} "
                        f"error={result.error_code or '-'}"
                    )
        if args.process:
            processing = pipeline.process(
                now - timedelta(days=2),
                now,
                version="cluster-v1",
                assessment_version="assessment-v1",
            )
            print(
                f"process clusters={processing.created_clusters} "
                f"items={processing.assigned_items} evidence={processing.created_evidence}"
            )
        if args.brief_date is not None:
            brief = pipeline.generate(
                args.brief_date,
                now=now,
                version="brief-v1-dry-run" if args.dry_run else "brief-v1",
            )
            print(
                f"brief status={brief.status.value} items={brief.item_count} "
                f"reading_seconds={brief.reading_time_seconds}"
            )
        if args.dry_run:
            session.rollback()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SoloPilot intelligence pipeline")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--process", action="store_true")
    parser.add_argument("--brief-date", type=parse_date)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not (args.collect or args.process or args.brief_date):
        parser.error("select --collect, --process, or --brief-date")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
