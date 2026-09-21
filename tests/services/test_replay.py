from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    CandidateStatus,
    ResolutionStatus,
    ReviewStatus,
    RunKind,
    RunStatus,
    Source,
    TrendLifecycle,
)
from app.models.tables import (
    CandidateObservation,
    CollectionRun,
    EntityCandidate,
    EntityResolutionAttempt,
    PipelineRun,
    RawFetch,
    RawPayload,
    SourceObservation,
    TrendCandidate,
    TrendEntity,
    TrendSnapshot,
)
from app.services.replay import (
    InvalidReplayRange,
    ReplayService,
    ReplayVersionConflict,
    _parse_payload,
)

T0_START = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
T0 = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
GEEKNEWS_FIXTURE = Path(__file__).parents[1] / "fixtures" / "geeknews_atom.xml"


def test_replay_reparses_geeknews_raw_payload() -> None:
    fetch = SimpleNamespace(
        collected_at=T0,
        parser_version="geeknews-atom-parser-v1",
        request_url="https://news.hada.io/rss/news",
    )

    items = _parse_payload(Source.GEEKNEWS, GEEKNEWS_FIXTURE.read_bytes(), fetch)

    assert len(items) == 2
    assert items[0].canonical_text.startswith("LangChain")
    assert items[0].source_url == "https://news.hada.io/topic?id=34041"


def seed_historical_projection(session: Session) -> tuple[TrendCandidate, TrendEntity]:
    raw_bytes = b"""<?xml version="1.0"?>
<rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item>
<title>historical entity</title>
<link>https://trends.google.com/trending/rss?geo=KR</link>
<pubDate>Sun, 20 Sep 2026 01:00:00 +0000</pubDate>
<ht:approx_traffic>100+</ht:approx_traffic>
</item></channel></rss>"""
    collection = CollectionRun(
        run_key="replay-google-t0",
        source=Source.GOOGLE_TRENDS,
        started_at=T0_START + timedelta(hours=1),
        completed_at=T0_START + timedelta(hours=1),
        status=RunStatus.SUCCEEDED,
    )
    payload = RawPayload(
        source=Source.GOOGLE_TRENDS,
        payload_hash=hashlib.sha256(raw_bytes).hexdigest(),
        raw_payload={
            "content_encoding": "base64",
            "data": base64.b64encode(raw_bytes).decode("ascii"),
        },
        collected_at=T0_START + timedelta(hours=1),
        source_timestamp=T0_START + timedelta(hours=1),
        collector_version="test",
        parser_version="google-rss-parser-v1",
    )
    live_run = PipelineRun(
        kind=RunKind.LIVE,
        as_of=T0_START + timedelta(hours=1, minutes=1),
        started_at=T0_START + timedelta(hours=1),
        completed_at=T0_START + timedelta(hours=1, minutes=1),
        status=RunStatus.SUCCEEDED,
        normalizer_version="normalizer-v1",
        entity_version="entity-v1",
        classifier_version="classifier-v1",
        score_version="score-v1",
        prompt_version="prompt-v1",
    )
    entity = TrendEntity(
        canonical_name="historical entity",
        normalized_name="historical entity",
        wikidata_id="Q_REPLAY_HISTORY",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        review_status=ReviewStatus.PENDING,
        version=1,
        created_at=T0,
        updated_at=T0,
    )
    current_entity = TrendEntity(
        canonical_name="later relink target",
        normalized_name="later relink target",
        wikidata_id="Q_REPLAY_LATER",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        review_status=ReviewStatus.PENDING,
        version=1,
        created_at=T0 + timedelta(days=1),
        updated_at=T0 + timedelta(days=1),
    )
    candidate = TrendCandidate(
        source=Source.GOOGLE_TRENDS,
        canonical_text="historical entity",
        normalized_text="historical entity",
        first_seen_at=T0_START + timedelta(hours=1),
        last_seen_at=T0_START + timedelta(hours=1),
        status=CandidateStatus.ACTIVE,
        resolution_status=ResolutionStatus.RESOLVED,
        normalizer_version="normalizer-v1",
        generation=1,
    )
    session.add_all([collection, payload, live_run, entity, current_entity, candidate])
    session.flush()
    session.add(
        RawFetch(
            run_id=collection.id,
            raw_payload_id=payload.id,
            request_url="https://trends.google.com/trending/rss?geo=KR",
            collected_at=T0_START + timedelta(hours=1),
            source_timestamp=T0_START + timedelta(hours=1),
            collector_version="test",
            parser_version="google-rss-parser-v1",
        )
    )
    observation = SourceObservation(
        run_id=collection.id,
        raw_payload_id=payload.id,
        source=Source.GOOGLE_TRENDS,
        source_item_id="replay-t0",
        canonical_text=candidate.canonical_text,
        source_timestamp=T0_START + timedelta(hours=1),
        observed_at=T0_START + timedelta(hours=1),
        source_url="https://trends.google.com/trending/rss?geo=KR",
        metrics={"approx_traffic_lower_bound": 100, "news_items": []},
    )
    session.add(observation)
    session.flush()
    session.add_all(
        [
            CandidateObservation(candidate_id=candidate.id, observation_id=observation.id),
            EntityCandidate(
                entity_id=current_entity.id,
                candidate_id=candidate.id,
                entity_version="entity-v2",
                match_reason="LATER_RELINK",
            ),
            EntityResolutionAttempt(
                candidate_id=candidate.id,
                pipeline_run_id=live_run.id,
                entity_id=entity.id,
                status=ResolutionStatus.RESOLVED,
                reason="EXACT_WIKIDATA",
                raw_fetch_ids=[],
                as_of=T0_START + timedelta(hours=1),
                attempted_at=T0_START + timedelta(hours=1, minutes=1),
            ),
        ]
    )
    session.commit()
    return candidate, entity


def test_replay_ignores_future_observation_and_current_relink(db_session: Session) -> None:
    candidate, historical_entity = seed_historical_projection(db_session)
    service = ReplayService(db_session, now=lambda: T0 + timedelta(days=3))

    first = service.run(T0_START, T0, score_version="score-replay-test", dry_run=True)

    future_collection = CollectionRun(
        run_key="replay-google-future",
        source=Source.GOOGLE_TRENDS,
        started_at=T0 + timedelta(days=1),
        completed_at=T0 + timedelta(days=1),
        status=RunStatus.SUCCEEDED,
    )
    future_raw = b"""<?xml version="1.0"?>
<rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item>
<title>historical entity</title>
<pubDate>Mon, 21 Sep 2026 12:00:00 +0000</pubDate>
<ht:approx_traffic>999999+</ht:approx_traffic>
</item></channel></rss>"""
    future_payload = RawPayload(
        source=Source.GOOGLE_TRENDS,
        payload_hash=hashlib.sha256(future_raw).hexdigest(),
        raw_payload={
            "content_encoding": "base64",
            "data": base64.b64encode(future_raw).decode("ascii"),
        },
        collected_at=T0 + timedelta(days=1),
        source_timestamp=T0 + timedelta(days=1),
        collector_version="test",
        parser_version="google-rss-parser-v1",
    )
    db_session.add_all([future_collection, future_payload])
    db_session.flush()
    db_session.add(
        RawFetch(
            run_id=future_collection.id,
            raw_payload_id=future_payload.id,
            request_url="https://trends.google.com/trending/rss?geo=KR",
            collected_at=T0 + timedelta(days=1),
            source_timestamp=T0 + timedelta(days=1),
            collector_version="test",
            parser_version="google-rss-parser-v1",
        )
    )
    future = SourceObservation(
        run_id=future_collection.id,
        raw_payload_id=future_payload.id,
        source=Source.GOOGLE_TRENDS,
        source_item_id="replay-future",
        canonical_text=candidate.canonical_text,
        source_timestamp=T0 + timedelta(days=1),
        observed_at=T0 + timedelta(days=1),
        source_url="https://trends.google.com/trending/rss?geo=KR",
        metrics={"approx_traffic_lower_bound": 999999, "news_items": []},
    )
    db_session.add(future)
    db_session.flush()
    db_session.add(CandidateObservation(candidate_id=candidate.id, observation_id=future.id))
    db_session.commit()

    second = service.run(T0_START, T0, score_version="score-replay-test", dry_run=True)

    assert first.snapshot_digest == second.snapshot_digest
    assert first.entity_ids == (historical_entity.id,)
    assert first.snapshot_count == 2
    assert (
        db_session.scalar(
            select(func.count()).select_from(PipelineRun).where(PipelineRun.kind == RunKind.REPLAY)
        )
        == 0
    )


def test_persisted_replay_has_isolated_run_identity(db_session: Session) -> None:
    _, entity = seed_historical_projection(db_session)

    result = ReplayService(db_session, now=lambda: T0 + timedelta(days=3)).run(
        T0_START, T0, score_version="score-replay-persist"
    )
    db_session.commit()

    run = db_session.get(PipelineRun, result.run_id)
    assert run is not None
    assert run.kind is RunKind.REPLAY
    assert run.status is RunStatus.SUCCEEDED
    assert run.snapshot_digest == result.snapshot_digest
    snapshot = db_session.scalar(
        select(TrendSnapshot).where(TrendSnapshot.pipeline_run_id == run.id)
    )
    assert snapshot is not None
    assert snapshot.entity_id == entity.id
    assert snapshot.score_version == "score-replay-persist"


def test_replay_uses_pre_range_raw_payload_as_baseline_warmup(
    db_session: Session,
) -> None:
    seed_historical_projection(db_session)
    service = ReplayService(db_session, now=lambda: T0 + timedelta(days=3))
    without_warmup = service.run(
        T0_START,
        T0,
        score_version="score-replay-warmup",
        dry_run=True,
    )
    warmup_time = T0_START - timedelta(days=10) + timedelta(hours=1)
    warmup_raw = b"""<?xml version="1.0"?>
<rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item>
<title>historical entity</title>
<pubDate>Thu, 10 Sep 2026 01:00:00 +0000</pubDate>
<ht:approx_traffic>100+</ht:approx_traffic>
</item></channel></rss>"""
    collection = CollectionRun(
        run_key="replay-google-warmup",
        source=Source.GOOGLE_TRENDS,
        started_at=warmup_time,
        completed_at=warmup_time,
        status=RunStatus.SUCCEEDED,
    )
    payload = RawPayload(
        source=Source.GOOGLE_TRENDS,
        payload_hash=hashlib.sha256(warmup_raw).hexdigest(),
        raw_payload={
            "content_encoding": "base64",
            "data": base64.b64encode(warmup_raw).decode("ascii"),
        },
        collected_at=warmup_time,
        source_timestamp=warmup_time,
        collector_version="test",
        parser_version="google-rss-parser-v1",
    )
    db_session.add_all([collection, payload])
    db_session.flush()
    db_session.add(
        RawFetch(
            run_id=collection.id,
            raw_payload_id=payload.id,
            request_url="https://trends.google.com/trending/rss?geo=KR",
            collected_at=warmup_time,
            source_timestamp=warmup_time,
            collector_version="test",
            parser_version="google-rss-parser-v1",
        )
    )
    db_session.commit()

    with_warmup = service.run(
        T0_START,
        T0,
        score_version="score-replay-warmup",
        dry_run=True,
    )

    assert without_warmup.snapshot_count == 2
    assert with_warmup.snapshot_count == 0
    assert with_warmup.snapshot_digest != without_warmup.snapshot_digest


def test_replay_rejects_unimplemented_pipeline_version(db_session: Session) -> None:
    seed_historical_projection(db_session)
    service = ReplayService(db_session, now=lambda: T0 + timedelta(days=3))

    with pytest.raises(ValueError, match="unsupported normalizer_version"):
        service.run(
            T0_START,
            T0,
            score_version="score-replay-versions",
            normalizer_version="normalizer-v2",
            dry_run=True,
        )

    assert db_session.scalar(select(func.count()).select_from(TrendSnapshot)) == 0


def test_replay_digest_covers_fetch_identity_and_acquisition_time(
    db_session: Session,
) -> None:
    seed_historical_projection(db_session)
    service = ReplayService(db_session, now=lambda: T0 + timedelta(days=3))
    first = service.run(
        T0_START,
        T0,
        score_version="score-replay-provenance",
        dry_run=True,
    )
    raw_fetch = db_session.scalar(select(RawFetch))
    assert raw_fetch is not None
    raw_fetch.collected_at += timedelta(minutes=1)
    db_session.commit()

    second = service.run(
        T0_START,
        T0,
        score_version="score-replay-provenance",
        dry_run=True,
    )

    assert first.snapshot_digest != second.snapshot_digest


def test_persisted_replay_rejects_existing_live_snapshot_version(
    db_session: Session,
) -> None:
    _, entity = seed_historical_projection(db_session)
    live_run_id = db_session.scalar(select(PipelineRun.id).where(PipelineRun.kind == RunKind.LIVE))
    assert live_run_id is not None
    db_session.add(
        TrendSnapshot(
            entity_id=entity.id,
            pipeline_run_id=live_run_id,
            as_of=T0,
            lifecycle=TrendLifecycle.NEW,
            total_score=55,
            breakdown={},
            missing_inputs=[],
            score_version="score-conflict",
            system_detected_at=T0,
        )
    )
    db_session.commit()

    with pytest.raises(ReplayVersionConflict, match="new score_version"):
        ReplayService(db_session, now=lambda: T0 + timedelta(days=3)).run(
            T0_START, T0, score_version="score-conflict"
        )


@pytest.mark.parametrize(
    ("from_", "to"),
    [
        (datetime(2026, 9, 20), T0),
        (T0_START, datetime(2026, 9, 20, 12)),
        (T0, T0_START),
    ],
)
def test_replay_rejects_naive_or_reverse_ranges(
    db_session: Session, from_: datetime, to: datetime
) -> None:
    with pytest.raises(InvalidReplayRange):
        ReplayService(db_session).run(from_, to, score_version="score-v1")
