from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import (
    CategoryAvailability,
    DataMode,
    FeedbackType,
    NotificationMode,
    ProductEventType,
    PublicationPolicyMode,
    RunStatus,
    Source,
)
from app.models.tables import Base, CollectionRun, RawPayload, SourceObservation

UTC_NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def test_same_run_source_item_is_idempotent(db_session) -> None:
    collection_run = CollectionRun(
        run_key="google:20260920T1200",
        source=Source.GOOGLE_TRENDS,
        started_at=UTC_NOW,
        status=RunStatus.RUNNING,
    )
    raw_payload = RawPayload(
        source=Source.GOOGLE_TRENDS,
        payload_hash="a" * 64,
        raw_payload={"feed": "fixture"},
        collected_at=UTC_NOW,
        source_timestamp=UTC_NOW,
        collector_version="google-rss-v1",
        parser_version="google-rss-parser-v1",
    )
    db_session.add_all([collection_run, raw_payload])
    db_session.flush()
    db_session.add_all(
        [
            SourceObservation(
                run_id=collection_run.id,
                raw_payload_id=raw_payload.id,
                source=Source.GOOGLE_TRENDS,
                source_item_id="google:term:20260920",
                canonical_text="term",
                source_timestamp=UTC_NOW,
                observed_at=UTC_NOW,
                source_url="https://trends.google.com/trending/rss?geo=KR",
                metrics={},
            ),
            SourceObservation(
                run_id=collection_run.id,
                raw_payload_id=raw_payload.id,
                source=Source.GOOGLE_TRENDS,
                source_item_id="google:term:20260920",
                canonical_text="term",
                source_timestamp=UTC_NOW,
                observed_at=UTC_NOW,
                source_url="https://trends.google.com/trending/rss?geo=KR",
                metrics={},
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_payload_hash_is_unique_per_source(db_session) -> None:
    payload = dict(
        source=Source.WIKIMEDIA,
        payload_hash="b" * 64,
        raw_payload={"items": []},
        collected_at=UTC_NOW,
        source_timestamp=UTC_NOW,
        collector_version="wikimedia-v1",
        parser_version="wikimedia-parser-v1",
    )
    db_session.add_all([RawPayload(**payload), RawPayload(**payload)])

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_schema_contains_replayable_pipeline_tables() -> None:
    expected = {
        "collection_runs",
        "raw_payloads",
        "raw_fetches",
        "source_observations",
        "pipeline_runs",
        "trend_candidates",
        "candidate_observations",
        "trend_entities",
        "entity_aliases",
        "entity_candidates",
        "entity_classifications",
        "trend_snapshots",
        "evidence",
        "claims",
        "claim_evidence",
        "claim_snapshots",
        "summary_cache",
        "reviews",
        "human_evaluations",
        "cost_records",
    }

    assert expected <= set(Base.metadata.tables)


def test_schema_contains_isolated_user_mvp_tables() -> None:
    expected = {
        "category_settings",
        "product_trend_cards",
        "anonymous_users",
        "user_interests",
        "notification_preferences",
        "trend_interactions",
        "trend_feedback",
        "saved_trends",
        "product_events",
    }

    assert expected <= set(Base.metadata.tables)


def test_user_mvp_enums_have_stable_operational_values() -> None:
    assert [item.value for item in DataMode] == ["LIVE", "DEMO", "TEST"]
    assert [item.value for item in CategoryAvailability] == [
        "ENABLED",
        "EXPERIMENTAL",
        "DISABLED",
    ]
    assert [item.value for item in PublicationPolicyMode] == [
        "MANUAL_APPROVAL_REQUIRED",
        "AUTO_PUBLISH_ELIGIBLE",
        "AUTO_PUBLISH",
    ]
    assert {item.value for item in FeedbackType} == {
        "NEW_AND_USEFUL",
        "ALREADY_KNEW",
        "NOT_INTERESTED",
        "INCORRECT",
    }
    assert {item.value for item in NotificationMode} == {
        "OFF",
        "DAILY_DIGEST",
        "IMPORTANT_RISING",
    }
    assert "FEEDBACK_INCORRECT" in {item.value for item in ProductEventType}


def test_user_records_are_tenant_scoped_and_mode_tagged() -> None:
    tables = Base.metadata.tables
    assert {"credential_hash", "created_at", "last_seen_at"} <= set(
        tables["anonymous_users"].columns.keys()
    )
    assert {"user_id", "card_id", "feedback_type"} <= set(
        tables["trend_feedback"].columns.keys()
    )
    assert "data_mode" in tables["product_trend_cards"].columns
    assert "data_mode" in tables["product_events"].columns
    assert {
        "previous_status",
        "resulting_status",
        "auto_pipeline_result",
        "product_card_id",
        "snapshot_id",
        "category_at_review",
    } <= set(tables["reviews"].columns.keys())


def test_derived_records_preserve_algorithm_versions() -> None:
    assert {
        "collector_version",
        "parser_version",
    } <= set(Base.metadata.tables["raw_payloads"].columns.keys())
    assert {
        "normalizer_version",
        "entity_version",
        "classifier_version",
        "score_version",
        "prompt_version",
    } <= set(Base.metadata.tables["pipeline_runs"].columns.keys())
    assert "classifier_version" in Base.metadata.tables["entity_classifications"].columns
    assert "score_version" in Base.metadata.tables["trend_snapshots"].columns
    assert "prompt_version" in Base.metadata.tables["claims"].columns


def test_evidence_has_exact_source_provenance_foreign_keys() -> None:
    evidence_columns = Base.metadata.tables["evidence"].columns

    assert "observation_id" in evidence_columns
    assert "resolution_attempt_id" in evidence_columns
    assert "raw_fetch_id" in evidence_columns
