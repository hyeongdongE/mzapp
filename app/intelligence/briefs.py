from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.intelligence.reading_time import ReadingTimeEstimator
from app.models.enums import EvidenceConfidence

CONFIDENCE_RANK = {
    EvidenceConfidence.STRONG: 2,
    EvidenceConfidence.SUPPORTED: 1,
    EvidenceConfidence.LOW: 0,
    EvidenceConfidence.REJECTED: -1,
}


@dataclass(frozen=True)
class BriefCandidate:
    event_id: int
    confidence: EvidenceConfidence
    importance: float
    first_seen_at: datetime
    rendered_text: str
    compact_text: str | None = None


@dataclass(frozen=True)
class BriefSelection:
    items: tuple[BriefCandidate, ...]
    reading_time_seconds: int
    used_compact_content: bool
    rejected: bool


class BriefSelector:
    def __init__(self, estimator: ReadingTimeEstimator | None = None) -> None:
        self._estimator = estimator or ReadingTimeEstimator()

    def rank(self, candidates: list[BriefCandidate]) -> list[BriefCandidate]:
        return sorted(
            candidates,
            key=lambda item: (
                -item.importance,
                -CONFIDENCE_RANK[item.confidence],
                -item.first_seen_at.timestamp(),
                item.event_id,
            ),
        )

    def select(self, candidates: list[BriefCandidate]) -> BriefSelection:
        selected = self.rank(candidates)[:7]
        seconds = self._seconds(selected, compact=False)
        used_compact = False
        if seconds > 300 and any(item.compact_text is not None for item in selected):
            compact_seconds = self._seconds(selected, compact=True)
            if compact_seconds < seconds:
                seconds = compact_seconds
                used_compact = True

        minimum = 3 if len(selected) >= 3 else len(selected)
        while seconds > 300 and len(selected) > minimum:
            selected.pop()
            seconds = self._seconds(selected, compact=used_compact)
        return BriefSelection(
            items=tuple(selected),
            reading_time_seconds=seconds,
            used_compact_content=used_compact,
            rejected=seconds > 300,
        )

    def _seconds(self, items: list[BriefCandidate], *, compact: bool) -> int:
        content = "\n".join(
            item.compact_text if compact and item.compact_text is not None else item.rendered_text
            for item in items
        )
        return self._estimator.estimate_seconds(content)
