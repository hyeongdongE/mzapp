from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.intelligence.briefs import BriefCandidate, BriefSelector
from app.models.enums import EvidenceConfidence

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def candidate(
    event_id: int,
    importance: float,
    *,
    seconds: int = 60,
    confidence: EvidenceConfidence = EvidenceConfidence.SUPPORTED,
    compact_seconds: int | None = None,
) -> BriefCandidate:
    return BriefCandidate(
        event_id=event_id,
        assessment_version="assessment-v1",
        confidence=confidence,
        importance=importance,
        first_seen_at=NOW + timedelta(minutes=event_id),
        rendered_text="가" * (seconds * 500 // 60),
        compact_text=(
            "가" * (compact_seconds * 500 // 60)
            if compact_seconds is not None
            else None
        ),
    )


def test_rank_orders_importance_then_confidence_recency_and_id() -> None:
    candidates = [
        candidate(3, 80, confidence=EvidenceConfidence.SUPPORTED),
        candidate(2, 80, confidence=EvidenceConfidence.STRONG),
        candidate(1, 90),
    ]

    ranked = BriefSelector().rank(candidates)

    assert [item.event_id for item in ranked] == [1, 2, 3]


def test_selection_removes_lowest_ranked_until_under_five_minutes() -> None:
    candidates = [candidate(index, 100 - index, seconds=70) for index in range(1, 6)]

    result = BriefSelector().select(candidates)

    assert [item.event_id for item in result.items] == [1, 2, 3, 4]
    assert result.reading_time_seconds <= 300
    assert result.rejected is False


def test_selection_rejects_when_three_items_still_exceed_limit() -> None:
    result = BriefSelector().select(
        [candidate(index, 100 - index, seconds=120) for index in range(1, 4)]
    )

    assert len(result.items) == 3
    assert result.reading_time_seconds > 300
    assert result.rejected is True


def test_selection_uses_bounded_compact_content_before_dropping_items() -> None:
    result = BriefSelector().select(
        [
            candidate(index, 100 - index, seconds=120, compact_seconds=90)
            for index in range(1, 4)
        ]
    )

    assert len(result.items) == 3
    assert result.used_compact_content is True
    assert result.reading_time_seconds == 270
    assert result.rejected is False


def test_selection_caps_normal_brief_at_seven_without_forcing_five() -> None:
    result = BriefSelector().select(
        [candidate(index, 100 - index, seconds=20) for index in range(1, 10)]
    )

    assert len(result.items) == 7
