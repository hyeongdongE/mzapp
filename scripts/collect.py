from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

import httpx

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


async def collect(source: str, as_of: datetime) -> list[dict[str, int | str]]:
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
                WikimediaTopPagesCollector(safe_http, str(settings.wikimedia_api_url))
            )
        for collector in collectors:
            run_key = f"{collector.source.value.lower()}:{as_of:%Y%m%dT%H%M%SZ}"
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
    args = parser.parse_args()
    for output in asyncio.run(collect(args.source, parse_as_of(args.as_of))):
        print(
            f"source={output['source']} run_id={output['run_id']} "
            f"observations={output['observations']}"
        )


if __name__ == "__main__":
    main()
