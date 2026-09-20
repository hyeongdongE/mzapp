from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
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
    EntityAlias,
    EntityCandidate,
    PipelineRun,
    RawPayload,
    SourceObservation,
    TrendCandidate,
    TrendEntity,
    TrendSnapshot,
)

NOW = datetime(2026, 9, 21, 2, tzinfo=UTC)


def seed_visible_entity(session: Session) -> TrendEntity:
    collection_run = CollectionRun(
        run_key="dashboard-google-run",
        source=Source.GOOGLE_TRENDS,
        started_at=NOW,
        completed_at=NOW,
        status=RunStatus.SUCCEEDED,
    )
    raw_payload = RawPayload(
        source=Source.GOOGLE_TRENDS,
        payload_hash="d" * 64,
        raw_payload={"encoding": "base64", "content": "PHJzcz4="},
        collected_at=NOW,
        source_timestamp=NOW,
        collector_version="google-rss-v1",
        parser_version="google-rss-v1",
    )
    run = PipelineRun(
        kind=RunKind.LIVE,
        as_of=NOW,
        started_at=NOW,
        completed_at=NOW,
        status=RunStatus.SUCCEEDED,
        normalizer_version="normalizer-v1",
        entity_version="entity-v1",
        classifier_version="classifier-v1",
        score_version="score-v1",
        prompt_version="prompt-v1",
    )
    entity = TrendEntity(
        canonical_name="검증 트렌드",
        normalized_name="검증 트렌드",
        wikidata_id="Q_DASHBOARD",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        review_status=ReviewStatus.PENDING,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    candidate = TrendCandidate(
        source=Source.GOOGLE_TRENDS,
        canonical_text="검증 트렌드 검색어",
        normalized_text="검증 트렌드 검색어",
        first_seen_at=NOW,
        last_seen_at=NOW,
        status=CandidateStatus.ACTIVE,
        resolution_status=ResolutionStatus.RESOLVED,
        normalizer_version="normalizer-v1",
        generation=1,
    )
    session.add_all([collection_run, raw_payload, run, entity, candidate])
    session.flush()
    observation = SourceObservation(
        run_id=collection_run.id,
        raw_payload_id=raw_payload.id,
        source=Source.GOOGLE_TRENDS,
        source_item_id="dashboard-item",
        canonical_text="검증 트렌드 검색어",
        source_timestamp=NOW,
        observed_at=NOW,
        source_url="https://trends.google.com/trending/rss?geo=KR",
        metrics={"approx_traffic": 100},
    )
    session.add(observation)
    session.flush()
    session.add_all(
        [
            EntityAlias(
                entity_id=entity.id,
                alias="검증 별칭",
                normalized_alias="검증 별칭",
                language="ko",
                source="WIKIDATA_ALIAS",
                approved=True,
            ),
            EntityCandidate(
                entity_id=entity.id,
                candidate_id=candidate.id,
                entity_version="entity-v1",
                match_reason="TEST_FIXTURE",
            ),
            CandidateObservation(
                candidate_id=candidate.id,
                observation_id=observation.id,
            ),
            TrendSnapshot(
                entity_id=entity.id,
                pipeline_run_id=run.id,
                as_of=NOW,
                lifecycle=TrendLifecycle.RISING,
                total_score=72.5,
                breakdown={
                    "interpretation": "internal_relative_score_not_probability",
                    "components": {"velocity": 0.8},
                },
                missing_inputs=[],
                score_version="score-v1",
                system_detected_at=NOW,
            ),
        ]
    )
    session.commit()
    return entity


def test_candidate_list_exposes_score_breakdown_and_source_attribution(
    client: TestClient, api_session: Session
) -> None:
    entity = seed_visible_entity(api_session)

    response = client.get("/candidates")

    assert response.status_code == 200
    assert entity.canonical_name in response.text
    assert "Google Trends" in response.text
    assert "내부 상대 점수" in response.text
    assert "72.5" in response.text
    assert "First seen" in response.text
    assert NOW.date().isoformat() in response.text


def test_detail_exposes_evidence_timestamp_and_score_interpretation(
    client: TestClient, api_session: Session
) -> None:
    entity = seed_visible_entity(api_session)

    response = client.get(f"/entities/{entity.id}")

    assert response.status_code == 200
    assert "확률이 아닌 내부 상대 점수" in response.text
    assert "trends.google.com" in response.text
    assert NOW.date().isoformat() in response.text
    assert "Raw signals" in response.text
    assert "approx_traffic" in response.text
    assert "검증 별칭" in response.text
    assert "Q_DASHBOARD" in response.text
    assert "AI summary" in response.text


def test_today_page_shows_required_supply_counters(
    client: TestClient, api_session: Session
) -> None:
    seed_visible_entity(api_session)

    response = client.get("/?date=2026-09-21")

    assert response.status_code == 200
    assert "Raw candidates" in response.text
    assert "Unique entities" in response.text
    assert "Published candidates" in response.text
    assert "Rejected candidates" in response.text
    assert 'id="raw-candidates">1<' in response.text
    assert 'id="unique-entities">1<' in response.text
    assert 'id="published-candidates">0<' in response.text
    assert 'id="rejected-candidates">0<' in response.text
