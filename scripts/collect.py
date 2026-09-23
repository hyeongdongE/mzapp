from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime

import httpx

from app.collectors.base import CollectorError
from app.collectors.geeknews import GeekNewsAtomCollector
from app.collectors.github_releases import GitHubReleasesCollector
from app.collectors.google_trends import GoogleTrendsRssCollector
from app.collectors.hacker_news import HackerNewsCollector
from app.collectors.http import SafeHttpClient
from app.collectors.official_feed import OfficialFeedCollector
from app.collectors.wikimedia import WikimediaTopPagesCollector
from app.config.settings import Settings, get_settings
from app.db import session_scope
from app.models.enums import Source
from app.services.collection import CollectionService
from app.services.intelligence_collection import IntelligenceCollectionService


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


def build_collectors(
    source: str,
    safe_http: SafeHttpClient,
    settings: Settings,
    *,
    target_date: date | None,
) -> list:
    collectors = []
    if source in {"google", "legacy-all"}:
        collectors.append(
            GoogleTrendsRssCollector(safe_http, str(settings.google_trends_rss_url))
        )
    if source in {"wikimedia", "legacy-all"}:
        collectors.append(
            WikimediaTopPagesCollector(
                safe_http,
                str(settings.wikimedia_api_url),
                target_date=target_date,
            )
        )
    if source in {"geeknews", "all"}:
        collectors.append(GeekNewsAtomCollector(safe_http, str(settings.geeknews_rss_url)))
    if source in {"hacker-news", "all"}:
        collectors.append(
            HackerNewsCollector(safe_http, base_url=str(settings.hacker_news_api_url))
        )
    if source in {"github", "all"}:
        collectors.extend(
            GitHubReleasesCollector(
                safe_http,
                repository=repository,
                api_base_url=str(settings.github_api_url),
            )
            for repository in settings.github_release_repositories
        )
    if source in {"cloudflare", "all"}:
        collectors.append(
            OfficialFeedCollector(
                Source.OFFICIAL_CLOUDFLARE,
                safe_http,
                str(settings.cloudflare_rss_url),
            )
        )
    if source in {"aws", "all"}:
        collectors.append(
            OfficialFeedCollector(
                Source.OFFICIAL_AWS,
                safe_http,
                str(settings.aws_rss_url),
            )
        )
    return collectors


async def collect(
    source: str, as_of: datetime, *, target_date: date | None = None
) -> list[dict[str, int | str]]:
    settings = get_settings()
    outputs: list[dict[str, int | str]] = []
    async with httpx.AsyncClient() as client:
        safe_http = SafeHttpClient(
            client,
            allowed_hosts={
                "trends.google.com",
                "wikimedia.org",
                "www.wikidata.org",
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
            source, safe_http, settings, target_date=target_date
        )
        for collector in collectors:
            logical_key = target_date.isoformat() if target_date else f"{as_of:%Y%m%dT%H%M%SZ}"
            collection_key = getattr(collector, "collection_key", None)
            instance_key = f":{collection_key}" if collection_key else ""
            run_key = f"{collector.source.value.lower()}{instance_key}:{logical_key}"
            with session_scope() as session:
                try:
                    if collector.source in {Source.GOOGLE_TRENDS, Source.WIKIMEDIA}:
                        result = await CollectionService(session).run(
                            collector, as_of=as_of, run_key=run_key
                        )
                        item_count = result.inserted_observations
                    else:
                        result = await IntelligenceCollectionService(session).run(
                            collector, as_of=as_of, run_key=run_key
                        )
                        item_count = result.inserted_raw_items
                except CollectorError as exc:
                    outputs.append(
                        {
                            "source": collector.source.value,
                            "run_id": 0,
                            "items": 0,
                            "error": exc.code,
                        }
                    )
                    continue
                outputs.append(
                    {
                        "source": collector.source.value,
                        "run_id": result.run_id,
                        "items": item_count,
                    }
                )
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect official trend signals")
    parser.add_argument(
        "--source",
        choices=(
            "geeknews",
            "hacker-news",
            "github",
            "cloudflare",
            "aws",
            "all",
            "google",
            "wikimedia",
            "legacy-all",
        ),
        default="all",
    )
    parser.add_argument("--as-of")
    parser.add_argument("--date", type=parse_date, help="exact Wikimedia target date (YYYY-MM-DD)")
    args = parser.parse_args()
    if args.date is not None and args.source not in {"wikimedia", "legacy-all"}:
        parser.error("--date requires --source wikimedia or legacy-all")
    outputs = asyncio.run(collect(args.source, parse_as_of(args.as_of), target_date=args.date))
    for output in outputs:
        error = output.get("error")
        print(
            f"source={output['source']} run_id={output['run_id']} "
            f"items={output['items']} status={'failed' if error else 'ok'} "
            f"error={error or '-'}"
        )
    if any(output.get("error") for output in outputs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
