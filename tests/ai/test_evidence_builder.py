from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.ai.evidence import EvidenceBuilder
from app.models.enums import (
    CandidateStatus,
    ResolutionStatus,
    ReviewStatus,
    RunKind,
    RunStatus,
    Source,
)
from app.models.tables import (
    CandidateObservation,
    CollectionRun,
    EntityCandidate,
    EntityResolutionAttempt,
    EntityResolutionAttemptRawFetch,
    PipelineRun,
    RawFetch,
    RawPayload,
    SourceObservation,
    TrendCandidate,
    TrendEntity,
)

AS_OF = datetime(2026, 9, 20, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("wikidata_collected_at", "expected_wikidata"),
    [
        (AS_OF - timedelta(minutes=5), True),
        (AS_OF + timedelta(seconds=1), False),
    ],
)
def test_builder_preserves_immutable_wikidata_provenance_and_excludes_future_data(
    db_session, wikidata_collected_at: datetime, expected_wikidata: bool
) -> None:
    google_run = CollectionRun(
        run_key="google:test",
        source=Source.GOOGLE_TRENDS,
        started_at=AS_OF,
        completed_at=AS_OF,
        status=RunStatus.SUCCEEDED,
    )
    google_payload = RawPayload(
        source=Source.GOOGLE_TRENDS,
        payload_hash="g" * 64,
        raw_payload={"encoding": "base64", "body": "AA=="},
        collected_at=AS_OF,
        source_timestamp=AS_OF,
        collector_version="google-v1",
        parser_version="google-parser-v1",
    )
    wikidata_run = CollectionRun(
        run_key="wikidata:test",
        source=Source.WIKIDATA,
        started_at=AS_OF - timedelta(minutes=5),
        completed_at=AS_OF - timedelta(minutes=4),
        status=RunStatus.SUCCEEDED,
    )
    wikidata_payload = RawPayload(
        source=Source.WIKIDATA,
        payload_hash="w" * 64,
        raw_payload={
            "content_encoding": "base64",
            "content_type": "application/octet-stream",
            "data": base64.b64encode(
                json.dumps(
                    {
                        "entities": {
                            "Q1": {
                                "labels": {"ko": {"value": "테스트 주제"}},
                                "descriptions": {"ko": {"value": "과거 설명"}},
                                "aliases": {},
                                "claims": {"P31": []},
                            }
                        }
                    }
                ).encode()
            ).decode(),
        },
        collected_at=wikidata_collected_at,
        source_timestamp=None,
        collector_version="wikidata-v1",
        parser_version="wikidata-parser-v1",
    )
    pipeline_run = PipelineRun(
        kind=RunKind.LIVE,
        as_of=AS_OF,
        started_at=AS_OF - timedelta(minutes=5),
        completed_at=AS_OF,
        status=RunStatus.SUCCEEDED,
        normalizer_version="normalizer-v1",
        entity_version="entity-v1",
        classifier_version="classifier-v1",
        score_version="score-v1",
        prompt_version="prompt-v1",
    )
    db_session.add_all(
        [google_run, google_payload, wikidata_run, wikidata_payload, pipeline_run]
    )
    db_session.flush()
    wikidata_url = "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q1"
    wikidata_fetch = RawFetch(
        run_id=wikidata_run.id,
        raw_payload_id=wikidata_payload.id,
        request_url=wikidata_url,
        collected_at=wikidata_collected_at,
        source_timestamp=None,
        collector_version="wikidata-v1",
        parser_version="wikidata-parser-v1",
    )
    observations = [
        SourceObservation(
            run_id=google_run.id,
            raw_payload_id=google_payload.id,
            source=Source.GOOGLE_TRENDS,
            source_item_id=f"item-{index}",
            canonical_text="테스트 주제",
            source_timestamp=timestamp,
            observed_at=timestamp,
            source_url="https://trends.google.com/trending/rss?geo=KR",
            metrics={"traffic": 100 + index},
        )
        for index, timestamp in enumerate(
            (AS_OF - timedelta(minutes=1), AS_OF + timedelta(minutes=1)), start=1
        )
    ]
    candidate = TrendCandidate(
        source=Source.GOOGLE_TRENDS,
        canonical_text="테스트 주제",
        normalized_text="테스트 주제",
        first_seen_at=AS_OF - timedelta(minutes=1),
        last_seen_at=AS_OF + timedelta(minutes=1),
        status=CandidateStatus.ACTIVE,
        resolution_status=ResolutionStatus.RESOLVED,
        normalizer_version="normalizer-v1",
        generation=1,
    )
    entity = TrendEntity(
        canonical_name="테스트 주제",
        normalized_name="테스트 주제",
        description="cutoff 이후 새 설명",
        wikidata_id="Q1",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=["Q5"],
        review_status=ReviewStatus.PENDING,
        version=1,
    )
    db_session.add_all([wikidata_fetch, candidate, entity, *observations])
    db_session.flush()
    db_session.add_all(
        [
            EntityCandidate(
                entity_id=entity.id,
                candidate_id=candidate.id,
                entity_version="entity-v1",
                match_reason="test",
            ),
            *[
                CandidateObservation(candidate_id=candidate.id, observation_id=row.id)
                for row in observations
            ],
        ]
    )
    attempt = EntityResolutionAttempt(
        candidate_id=candidate.id,
        pipeline_run_id=pipeline_run.id,
        entity_id=entity.id,
        status=ResolutionStatus.RESOLVED,
        reason="UNIQUE_WIKIDATA_MATCH",
        raw_fetch_ids=[wikidata_fetch.id],
        as_of=AS_OF,
        attempted_at=AS_OF - timedelta(minutes=4),
    )
    db_session.add(attempt)
    db_session.flush()
    db_session.add(
        EntityResolutionAttemptRawFetch(
            attempt_id=attempt.id,
            raw_fetch_id=wikidata_fetch.id,
        )
    )

    built = EvidenceBuilder(db_session).build(entity, AS_OF)

    expected_kinds = ["TREND_SIGNAL", "WIKIDATA_ENTITY"] if expected_wikidata else ["TREND_SIGNAL"]
    assert [row.kind for row in built] == expected_kinds
    signal = built[0]
    assert signal.observation_id == observations[0].id
    assert signal.source_url == "https://trends.google.com/trending/rss?geo=KR"
    assert signal.fact["metrics"] == {"traffic": 101}
    if expected_wikidata:
        wikidata = built[1]
        assert wikidata.source is Source.WIKIDATA
        assert wikidata.source_url == wikidata_url
        assert wikidata.resolution_attempt_id == attempt.id
        assert wikidata.raw_fetch_id == wikidata_fetch.id
        assert wikidata.fact["wikidata_id"] == "Q1"
        assert wikidata.fact["description"] == "과거 설명"
