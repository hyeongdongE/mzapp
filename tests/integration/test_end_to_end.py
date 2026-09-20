from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.collectors.google_trends import GoogleTrendsRssCollector
from app.collectors.http import SafeHttpClient
from app.collectors.wikidata import WikidataLookup, WikidataMatch
from app.collectors.wikimedia import WikimediaTopPagesCollector
from app.evaluation.database import evaluate_day
from app.evaluation.reports import render_daily_markdown
from app.models.enums import HumanEvaluationLabel, ReviewAction
from app.models.tables import Claim, HumanEvaluation, TrendEntity, TrendSnapshot
from app.services.collection import CollectionService
from app.services.pipeline import PipelineService
from app.services.reviews import ReviewCommand, ReviewService

AS_OF = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class FakeWikidata:
    collector_version = "wikidata-api-v1"

    def __init__(self) -> None:
        self._ids: dict[str, str] = {}

    async def lookup(self, query: str) -> WikidataLookup:
        entity_id = self._ids.setdefault(query, f"Q{10000 + len(self._ids)}")
        return WikidataLookup(
            matches=[WikidataMatch(entity_id, query, (), None, ())],
            raw_responses=[],
        )


async def exercise_end_to_end(session: Session) -> str:
    before = evaluate_day(session, AS_OF.date())
    before_claims = session.scalar(select(func.count()).select_from(Claim)) or 0
    bodies = {
        "trends.google.com": (FIXTURES / "google_trends_rss.xml").read_bytes(),
        "wikimedia.org": (FIXTURES / "wikimedia_top_kr.json").read_bytes(),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=bodies[request.url.host], request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        safe_http = SafeHttpClient(
            client,
            allowed_hosts={"trends.google.com", "wikimedia.org"},
            max_bytes=2_000_000,
            retries=0,
        )
        google = await GoogleTrendsRssCollector(
            safe_http,
            "https://trends.google.com/trending/rss?geo=KR",
            now=lambda: AS_OF,
        ).collect(AS_OF)
        wikimedia = await WikimediaTopPagesCollector(
            safe_http,
            "https://wikimedia.org/api/rest_v1",
            now=lambda: AS_OF,
            target_date=AS_OF.date().replace(day=18),
        ).collect(AS_OF)
    CollectionService(session).persist(google, run_key="e2e-google")
    CollectionService(session).persist(wikimedia, run_key="e2e-wikimedia")
    run = await PipelineService(
        session,
        FakeWikidata(),
        now=lambda: AS_OF,
    ).build_entities(AS_OF)
    snapshot = session.scalar(
        select(TrendSnapshot)
        .where(TrendSnapshot.pipeline_run_id == run.id)
        .order_by(TrendSnapshot.total_score.desc())
    )
    assert snapshot is not None
    entity = session.get(TrendEntity, snapshot.entity_id)
    assert entity is not None
    ReviewService(session).apply(
        ReviewCommand(
            entity_id=entity.id,
            action=ReviewAction.APPROVE,
            expected_version=entity.version,
            actor="e2e-reviewer",
        ),
        AS_OF,
    )
    session.add(
        HumanEvaluation(
            entity_id=entity.id,
            label=HumanEvaluationLabel.VALID_TREND,
            actor="e2e-reviewer",
            created_at=AS_OF,
        )
    )
    session.flush()
    result = evaluate_day(session, AS_OF.date())
    report = render_daily_markdown(result)
    assert result.complete_day is True
    assert result.supply.raw_candidates - before.supply.raw_candidates == 4
    assert result.supply.unique_candidates - before.supply.unique_candidates == 2
    assert result.supply.trend_entities - before.supply.trend_entities == 2
    assert result.supply.approved_cards - before.supply.approved_cards == 1
    assert result.quality.valid_trends - before.quality.valid_trends == 1
    assert (session.scalar(select(func.count()).select_from(Claim)) or 0) > before_claims
    assert "Decision: `CONTINUE_DATA_COLLECTION`" in report
    return report


@pytest.mark.asyncio
async def test_fixture_collection_through_report(db_session: Session) -> None:
    await exercise_end_to_end(db_session)


@pytest.mark.asyncio
@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL is required for PostgreSQL end-to-end verification",
)
async def test_postgres_collection_through_report_rolls_back() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    with Session(engine) as session:
        await exercise_end_to_end(session)
        session.rollback()
    engine.dispose()
