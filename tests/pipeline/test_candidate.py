from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.enums import CandidateStatus, RunStatus, Source
from app.models.tables import (
    CandidateObservation,
    CollectionRun,
    RawPayload,
    SourceObservation,
)
from app.pipeline.candidate import CandidateGenerator

AS_OF = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def add_observation(
    db_session,
    *,
    item_id: str,
    text: str,
    source_timestamp: datetime,
    observed_at: datetime = AS_OF,
):
    run = CollectionRun(
        run_key=f"test:{item_id}",
        source=Source.GOOGLE_TRENDS,
        started_at=AS_OF,
        completed_at=AS_OF,
        status=RunStatus.SUCCEEDED,
    )
    payload = RawPayload(
        source=Source.GOOGLE_TRENDS,
        payload_hash=item_id.ljust(64, "0")[:64],
        raw_payload={"data": ""},
        collected_at=AS_OF,
        source_timestamp=source_timestamp,
        collector_version="test",
        parser_version="test",
    )
    db_session.add_all([run, payload])
    db_session.flush()
    observation = SourceObservation(
        run_id=run.id,
        raw_payload_id=payload.id,
        source=Source.GOOGLE_TRENDS,
        source_item_id=item_id,
        canonical_text=text,
        source_timestamp=source_timestamp,
        observed_at=observed_at,
        source_url="https://trends.google.com/trending/rss?geo=KR",
        metrics={},
    )
    db_session.add(observation)
    db_session.flush()
    return observation


def test_candidate_reuses_exact_source_normalized_text_and_links_each_observation(db_session):
    first = add_observation(
        db_session, item_id="one", text="ＡＩ・Tech", source_timestamp=AS_OF - timedelta(hours=1)
    )
    second = add_observation(db_session, item_id="two", text="AI Tech", source_timestamp=AS_OF)
    generator = CandidateGenerator(db_session)

    candidate = generator.generate(first)
    same_candidate = generator.generate(second)
    generator.generate(second)

    assert same_candidate.id == candidate.id
    assert candidate.canonical_text == first.canonical_text
    assert candidate.normalized_text == "ai tech"
    assert candidate.status is CandidateStatus.NEW
    assert candidate.first_seen_at == AS_OF - timedelta(hours=1)
    assert candidate.last_seen_at == AS_OF
    assert db_session.scalar(select(func.count()).select_from(CandidateObservation)) == 2
