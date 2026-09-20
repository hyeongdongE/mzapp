from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime

import httpx

from app.collectors.base import CollectorError
from app.collectors.google_trends import GoogleTrendsRssCollector
from app.collectors.http import SafeHttpClient
from app.collectors.wikimedia import WikimediaTopPagesCollector
from app.config.settings import get_settings
from app.db import session_scope
from app.services.collection import CollectionService


def parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--as-of must include a timezone")
    return parsed.astimezone(UTC)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--date must use YYYY-MM-DD") from exc


async def collect(
    source: str, as_of: datetime, *, target_date: date | None = None
) -> list[dict[str, int | str]]:
    settings = get_settings()
    outputs: list[dict[str, int | str]] = []
    async with httpx.AsyncClient() as client:
        safe_http = SafeHttpClient(
            client,
            allowed_hosts={"trends.google.com", "wikimedia.org", "www.wikidata.org"},
            max_bytes=settings.http_max_bytes,
            retries=settings.http_retries,
            timeout_seconds=settings.http_timeout_seconds,
            user_agent=settings.user_agent,
        )
        collectors = []
        if source in {"google", "all"}:
            collectors.append(
                GoogleTrendsRssCollector(safe_http, str(settings.google_trends_rss_url))
            )
        if source in {"wikimedia", "all"}:
            collectors.append(
                WikimediaTopPagesCollector(
                    safe_http,
                    str(settings.wikimedia_api_url),
                    target_date=target_date,
                )
            )
        for collector in collectors:
            logical_key = target_date.isoformat() if target_date else f"{as_of:%Y%m%dT%H%M%SZ}"
            run_key = f"{collector.source.value.lower()}:{logical_key}"
            with session_scope() as session:
                result = await CollectionService(session).run(
                    collector, as_of=as_of, run_key=run_key
                )
                outputs.append(
                    {
                        "source": collector.source.value,
                        "run_id": result.run_id,
                        "observations": result.inserted_observations,
                    }
                )
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect official trend signals")
    parser.add_argument("--source", choices=("google", "wikimedia", "all"), default="all")
    parser.add_argument("--as-of")
    parser.add_argument("--date", type=parse_date, help="exact Wikimedia target date (YYYY-MM-DD)")
    args = parser.parse_args()
    if args.date is not None and args.source != "wikimedia":
        parser.error("--date requires --source wikimedia")
    try:
        outputs = asyncio.run(collect(args.source, parse_as_of(args.as_of), target_date=args.date))
    except CollectorError as exc:
        parser.exit(1, f"collection failed: {exc.code}\n")
    for output in outputs:
        print(
            f"source={output['source']} run_id={output['run_id']} "
            f"observations={output['observations']}"
        )


if __name__ == "__main__":
    main()
