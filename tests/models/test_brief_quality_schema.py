from __future__ import annotations

from app.models.enums import (
    BriefItemUsefulness,
    BriefReviewSessionStatus,
    DuplicateEscapeVerdict,
    EventSelectionVerdict,
    EvidenceSetUsefulness,
    FactCorrectness,
    IncorrectMergeVerdict,
    InterpretationQuality,
    MissingEventDiscoverySource,
    VerbosityVerdict,
    WatchUsefulness,
)
from app.models.tables import Base


def test_brief_quality_enums_have_closed_values() -> None:
    assert [item.value for item in BriefReviewSessionStatus] == ["OPEN", "COMPLETED"]
    assert [item.value for item in BriefItemUsefulness] == ["USEFUL", "NOT_USEFUL"]
    assert [item.value for item in EventSelectionVerdict] == ["KEEP", "SHOULD_EXCLUDE", "UNSURE"]
    assert [item.value for item in FactCorrectness] == [
        "CORRECT", "PARTIALLY_CORRECT", "INCORRECT", "UNVERIFIABLE"
    ]
    assert [item.value for item in InterpretationQuality] == [
        "STRONG", "ACCEPTABLE", "WEAK", "MISLEADING"
    ]
    assert [item.value for item in WatchUsefulness] == [
        "ACTIONABLE", "USEFUL", "GENERIC", "NOT_USEFUL"
    ]
    assert [item.value for item in VerbosityVerdict] == [
        "TOO_SHORT", "JUST_RIGHT", "TOO_LONG"
    ]
    assert [item.value for item in EvidenceSetUsefulness] == [
        "ESSENTIAL", "HELPFUL", "REDUNDANT", "NOT_USEFUL"
    ]
    assert [item.value for item in IncorrectMergeVerdict] == [
        "NO_INCORRECT_MERGE", "INCORRECT_MERGE", "UNSURE"
    ]
    assert [item.value for item in DuplicateEscapeVerdict] == [
        "NO_DUPLICATE_ESCAPE", "DUPLICATE_ESCAPE", "UNSURE"
    ]
    assert [item.value for item in MissingEventDiscoverySource] == [
        "GEEKNEWS", "HACKER_NEWS", "GITHUB", "OFFICIAL_WEB", "X", "ARXIV",
        "HUGGING_FACE", "REDDIT", "OTHER",
    ]


def test_schema_contains_brief_quality_tables_and_constraints() -> None:
    expected = {
        "brief_review_sessions",
        "brief_review_reopens",
        "brief_review_activity_pulses",
        "brief_item_reviews",
        "brief_item_review_merge_memberships",
        "missing_event_reviews",
    }
    assert expected <= set(Base.metadata.tables)
    assert "pipeline_version" in Base.metadata.tables["daily_briefs"].columns

    names = {
        constraint.name
        for table_name in expected
        for constraint in Base.metadata.tables[table_name].constraints
    }
    assert {
        "uq_brief_review_session_brief_reviewer",
        "uq_brief_review_activity_event",
        "ck_brief_review_activity_seconds",
        "uq_brief_item_review_session_item",
        "uq_brief_item_review_merge_membership",
        "uq_missing_event_review_session_url",
    } <= names


def test_structured_defect_provenance_foreign_keys_are_present() -> None:
    review = Base.metadata.tables["brief_item_reviews"]
    memberships = Base.metadata.tables["brief_item_review_merge_memberships"]
    assert {fk.target_fullname for fk in review.foreign_keys} == {
        "brief_review_sessions.id",
        "brief_items.id",
        "event_clusters.id",
    }
    assert {fk.target_fullname for fk in memberships.foreign_keys} == {
        "brief_item_reviews.id",
        "event_cluster_items.id",
    }
