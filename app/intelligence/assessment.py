from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.sources import SOURCE_REGISTRY
from app.models.enums import ClusterStatus, EvidenceConfidence, EvidenceKind
from app.models.tables import EventAssessment, EventCluster, EventEvidence, RawItem

AUTHORITY = {
    EvidenceKind.OFFICIAL: 0.95,
    EvidenceKind.PRIMARY: 0.9,
    EvidenceKind.DEVELOPER: 0.85,
    EvidenceKind.COMMUNITY: 0.45,
    EvidenceKind.SECONDARY: 0.4,
    EvidenceKind.EARLY_SIGNAL: 0.25,
}
IMPORTANCE_SIGNALS = {
    "breaking": 20.0,
    "critical": 25.0,
    "deprecated": 20.0,
    "launch": 20.0,
    "model": 10.0,
    "outage": 25.0,
    "pricing": 15.0,
    "release": 15.0,
    "released": 15.0,
    "security": 25.0,
}


@dataclass(frozen=True)
class EventAssessmentResult:
    confidence: EvidenceConfidence
    confidence_breakdown: dict[str, float | str | bool]
    importance: float
    importance_breakdown: dict[str, float | str | bool]


class AssessmentService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def assess(self, event_id: int, *, version: str) -> EventAssessmentResult:
        existing = self._session.scalar(
            select(EventAssessment).where(
                EventAssessment.event_cluster_id == event_id,
                EventAssessment.assessment_version == version,
            )
        )
        if existing is not None:
            return _result(existing)

        cluster = self._session.get(EventCluster, event_id)
        if cluster is None:
            raise ValueError("event does not exist")
        rows = self._session.execute(
            select(EventEvidence, RawItem)
            .join(RawItem, RawItem.id == EventEvidence.raw_item_id)
            .where(
                EventEvidence.event_cluster_id == event_id,
                EventEvidence.publishable.is_(True),
            )
        ).all()
        confidence, confidence_breakdown = _confidence(rows, cluster.status)
        importance, importance_breakdown = _importance([item for _, item in rows])
        assessment = EventAssessment(
            event_cluster_id=event_id,
            confidence=confidence,
            confidence_breakdown=confidence_breakdown,
            importance=importance,
            importance_breakdown=importance_breakdown,
            assessment_version=version,
            assessed_at=datetime.now(UTC),
        )
        self._session.add(assessment)
        self._session.flush()
        return EventAssessmentResult(
            confidence,
            confidence_breakdown,
            importance,
            importance_breakdown,
        )


def _confidence(
    rows: list[tuple[EventEvidence, RawItem]], status: ClusterStatus
) -> tuple[EvidenceConfidence, dict[str, float | str | bool]]:
    collapsed: dict[str, tuple[EventEvidence, RawItem]] = {}
    for evidence, item in rows:
        current = collapsed.get(item.canonical_url)
        if current is None or AUTHORITY[evidence.kind] > AUTHORITY[current[0].kind]:
            collapsed[item.canonical_url] = (evidence, item)
    independent = list(collapsed.values())
    source_types = {
        SOURCE_REGISTRY[item.source].source_type.value for _, item in independent
    }
    authority = max((AUTHORITY[evidence.kind] for evidence, _ in independent), default=0.0)
    diversity_bonus = min(0.2, max(0, len(source_types) - 1) * 0.1)
    corroboration_bonus = min(0.1, max(0, len(independent) - 1) * 0.05)
    syndication_penalty = (
        (len(rows) - len(independent)) / len(rows) * 0.5 if rows else 0.0
    )
    ambiguity_penalty = 0.3 if status is ClusterStatus.NEEDS_REVIEW else 0.0
    score = max(
        0.0,
        min(
            1.0,
            authority
            + diversity_bonus
            + corroboration_bonus
            - syndication_penalty
            - ambiguity_penalty,
        ),
    )
    if not independent:
        confidence = EvidenceConfidence.REJECTED
    elif score >= 0.8 and (len(independent) >= 2 or authority >= 0.9):
        confidence = EvidenceConfidence.STRONG
    elif score >= 0.55:
        confidence = EvidenceConfidence.SUPPORTED
    else:
        confidence = EvidenceConfidence.LOW
    return confidence, {
        "score": round(score, 4),
        "independent_evidence_count": float(len(independent)),
        "independent_source_type_count": float(len(source_types)),
        "authority": authority,
        "diversity_bonus": diversity_bonus,
        "corroboration_bonus": corroboration_bonus,
        "syndication_penalty": syndication_penalty,
        "ambiguity_penalty": ambiguity_penalty,
    }


def _importance(
    items: list[RawItem],
) -> tuple[float, dict[str, float | str | bool]]:
    titles = sorted({item.normalized_title for item in items})
    text = " ".join(titles)
    matched = sorted(signal for signal in IMPORTANCE_SIGNALS if signal in text)
    signal_score = sum(IMPORTANCE_SIGNALS[signal] for signal in matched)
    score = min(100.0, 10.0 + signal_score)
    return score, {
        "base_score": 10.0,
        "signal_score": signal_score,
        "matched_signals": ",".join(matched),
        "score": score,
    }


def _result(assessment: EventAssessment) -> EventAssessmentResult:
    return EventAssessmentResult(
        assessment.confidence,
        assessment.confidence_breakdown,
        assessment.importance,
        assessment.importance_breakdown,
    )
