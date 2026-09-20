from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.ai.contracts import UNKNOWN_CAUSE_MESSAGE
from app.collectors.wikidata import WikidataLookup, WikidataMatch, WikidataRawResponse
from app.models.enums import RunKind, RunStatus
from app.models.tables import (
    Claim,
    EntityResolutionAttempt,
    EntityResolutionAttemptRawFetch,
    Evidence,
    PipelineRun,
    RawFetch,
    TrendEntity,
    TrendSnapshot,
)
from app.pipeline.candidate import CandidateGenerator
from app.services.pipeline import PipelineService, observations_for_replay
from tests.pipeline.test_candidate import AS_OF, add_observation


def test_observations_for_replay_enforces_cutoff_and_order(db_session) -> None:
    before = add_observation(
        db_session, item_id="before", text="before", source_timestamp=AS_OF - timedelta(minutes=1)
    )
    add_observation(
        db_session, item_id="after", text="after", source_timestamp=AS_OF + timedelta(minutes=1)
    )
    add_observation(
        db_session,
        item_id="learned-later",
        text="learned later",
        source_timestamp=AS_OF - timedelta(days=1),
        observed_at=AS_OF + timedelta(minutes=1),
    )

    results = observations_for_replay(db_session, AS_OF)

    assert [observation.id for observation in results] == [before.id]


def test_observations_for_replay_rejects_naive_or_non_utc_cutoff(db_session) -> None:
    with pytest.raises(ValueError, match="aware UTC"):
        observations_for_replay(db_session, datetime(2026, 9, 20, 12, 0))
    with pytest.raises(ValueError, match="aware UTC"):
        observations_for_replay(
            db_session,
            datetime(2026, 9, 20, 12, 0, tzinfo=timezone(timedelta(hours=9))),
        )


@pytest.mark.asyncio
async def test_pipeline_persists_versions_entity_and_wikidata_raw_fetches(db_session) -> None:
    add_observation(db_session, item_id="entity", text="이현중", source_timestamp=AS_OF)

    class FakeWikidata:
        collector_version = "wikidata-api-v1"

        async def lookup(self, _query: str) -> WikidataLookup:
            return WikidataLookup(
                matches=[
                    WikidataMatch(
                        "Q123",
                        "이현중",
                        ("Lee Hyunjung",),
                        "대한민국의 농구 선수",
                        ("Q5",),
                    )
                ],
                raw_responses=[
                    WikidataRawResponse(
                        "https://www.wikidata.org/w/api.php?action=wbsearchentities",
                        b'{"search":[]}',
                        AS_OF,
                    )
                ],
            )

    run = await PipelineService(
        db_session,
        FakeWikidata(),
        now=lambda: AS_OF + timedelta(seconds=1),
    ).build_entities(AS_OF)

    assert run.status is RunStatus.SUCCEEDED
    assert run.normalizer_version == "normalizer-v1"
    assert db_session.scalar(select(func.count()).select_from(PipelineRun)) == 1
    assert db_session.scalar(select(func.count()).select_from(TrendEntity)) == 1
    assert db_session.scalar(select(func.count()).select_from(RawFetch)) == 1
    snapshot = db_session.scalar(select(TrendSnapshot))
    assert snapshot is not None
    assert snapshot.breakdown["interpretation"] == "internal_relative_score_not_probability"
    attempt = db_session.scalar(select(EntityResolutionAttempt))
    assert attempt is not None
    assert attempt.pipeline_run_id == run.id
    assert attempt.entity_id is not None
    assert attempt.as_of.replace(tzinfo=UTC) == AS_OF
    assert attempt.attempted_at.replace(tzinfo=UTC) == AS_OF + timedelta(seconds=1)
    assert len(attempt.raw_fetch_ids) == 1
    raw_link = db_session.scalar(select(EntityResolutionAttemptRawFetch))
    assert raw_link is not None
    assert raw_link.attempt_id == attempt.id
    assert raw_link.raw_fetch_id == attempt.raw_fetch_ids[0]
    evidence = list(db_session.scalars(select(Evidence).order_by(Evidence.kind)))
    assert {row.kind for row in evidence} == {"TREND_SIGNAL"}
    claims = list(db_session.scalars(select(Claim).order_by(Claim.kind)))
    assert {claim.kind for claim in claims} == {"CAUSE", "INTEREST"}
    unknown_cause = next(claim for claim in claims if claim.kind == "CAUSE")
    assert unknown_cause.text == UNKNOWN_CAUSE_MESSAGE
    assert unknown_cause.publishable is True


@pytest.mark.asyncio
async def test_entity_replay_is_blocked_until_historical_projection_exists(db_session) -> None:
    class UnexpectedWikidata:
        collector_version = "wikidata-api-v1"

        async def lookup(self, _query: str):
            raise AssertionError("replay must not call live Wikidata")

    with pytest.raises(ValueError, match="historical entity projection"):
        await PipelineService(db_session, UnexpectedWikidata()).build_entities(
            AS_OF, kind=RunKind.REPLAY
        )

    assert db_session.scalar(select(func.count()).select_from(PipelineRun)) == 0


@pytest.mark.asyncio
async def test_live_pipeline_rejects_stale_cutoff_before_creating_run(db_session) -> None:
    class UnexpectedWikidata:
        collector_version = "wikidata-api-v1"

        async def lookup(self, _query: str):
            raise AssertionError("stale live cutoff must not call Wikidata")

    with pytest.raises(ValueError, match="historical entity projection"):
        await PipelineService(
            db_session,
            UnexpectedWikidata(),
            now=lambda: AS_OF + timedelta(minutes=6),
        ).build_entities(AS_OF)

    assert db_session.scalar(select(func.count()).select_from(PipelineRun)) == 0


@pytest.mark.asyncio
async def test_live_pipeline_rejects_future_cutoff_before_creating_run(db_session) -> None:
    class UnexpectedWikidata:
        collector_version = "wikidata-api-v1"

        async def lookup(self, _query: str):
            raise AssertionError("future cutoff must not call Wikidata")

    with pytest.raises(ValueError, match="future"):
        await PipelineService(
            db_session,
            UnexpectedWikidata(),
            now=lambda: AS_OF - timedelta(minutes=6),
        ).build_entities(AS_OF)

    assert db_session.scalar(select(func.count()).select_from(PipelineRun)) == 0


@pytest.mark.asyncio
async def test_targeted_smoke_resolves_only_requested_candidate(db_session) -> None:
    first_observation = add_observation(
        db_session, item_id="target-first", text="first", source_timestamp=AS_OF
    )
    add_observation(
        db_session, item_id="target-second", text="second", source_timestamp=AS_OF
    )
    target = CandidateGenerator(db_session).generate(first_observation)

    class FakeWikidata:
        collector_version = "wikidata-api-v1"

        async def lookup(self, query: str) -> WikidataLookup:
            return WikidataLookup(
                matches=[WikidataMatch("Q_TARGET", query, (), None, ())],
                raw_responses=[],
            )

    await PipelineService(
        db_session, FakeWikidata(), now=lambda: AS_OF
    ).build_entities(AS_OF, candidate_id=target.id)

    attempts = list(db_session.scalars(select(EntityResolutionAttempt)))
    assert len(attempts) == 1
    assert attempts[0].candidate_id == target.id
