from __future__ import annotations

import argparse
import asyncio

import httpx

from app.collectors.http import SafeHttpClient
from app.collectors.wikidata import WikidataClient
from app.config.settings import get_settings
from app.db import session_scope
from app.services.pipeline import PipelineService
from scripts.collect import parse_as_of


async def build(
    as_of_text: str | None, max_candidates: int | None, candidate_id: int | None
) -> None:
    settings = get_settings()
    as_of = parse_as_of(as_of_text)
    async with httpx.AsyncClient() as client:
        safe_http = SafeHttpClient(
            client,
            allowed_hosts={"www.wikidata.org", "wikidata.org"},
            max_bytes=settings.http_max_bytes,
            retries=settings.http_retries,
            timeout_seconds=settings.http_timeout_seconds,
            user_agent=settings.user_agent,
        )
        wikidata = WikidataClient(safe_http, str(settings.wikidata_api_url))
        with session_scope() as session:
            run = await PipelineService(session, wikidata).build_entities(
                as_of, max_candidates=max_candidates, candidate_id=candidate_id
            )
            print(f"pipeline_run={run.id} status={run.status.value} as_of={run.as_of.isoformat()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build normalized entities from stored observations"
    )
    parser.add_argument("--as-of")
    parser.add_argument(
        "--max-candidates",
        type=int,
        help="optional live-smoke cap; omit for a complete pipeline run",
    )
    parser.add_argument(
        "--candidate-id",
        type=int,
        help="optional targeted live-smoke candidate id",
    )
    args = parser.parse_args()
    if args.max_candidates is not None and args.max_candidates < 1:
        parser.error("--max-candidates must be positive")
    if args.candidate_id is not None and args.candidate_id < 1:
        parser.error("--candidate-id must be positive")
    asyncio.run(build(args.as_of, args.max_candidates, args.candidate_id))


if __name__ == "__main__":
    main()
