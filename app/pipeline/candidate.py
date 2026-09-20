from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import CandidateStatus, ResolutionStatus
from app.models.tables import CandidateObservation, SourceObservation, TrendCandidate
from app.pipeline.normalization import normalize_text


class CandidateGenerator:
    normalizer_version = "normalizer-v1"

    def __init__(self, session: Session) -> None:
        self._session = session

    def generate(self, observation: SourceObservation) -> TrendCandidate:
        normalized = normalize_text(observation.canonical_text)
        if not normalized:
            raise ValueError("candidate text has no normalizable content")
        candidate = self._session.scalar(
            select(TrendCandidate).where(
                TrendCandidate.source == observation.source,
                TrendCandidate.normalized_text == normalized,
            )
        )
        if candidate is None:
            candidate = TrendCandidate(
                source=observation.source,
                canonical_text=observation.canonical_text,
                normalized_text=normalized,
                first_seen_at=observation.source_timestamp,
                last_seen_at=observation.source_timestamp,
                status=CandidateStatus.NEW,
                resolution_status=ResolutionStatus.NEEDS_REVIEW,
                normalizer_version=self.normalizer_version,
            )
            self._session.add(candidate)
            self._session.flush()
        else:
            candidate.first_seen_at = min(candidate.first_seen_at, observation.source_timestamp)
            candidate.last_seen_at = max(candidate.last_seen_at, observation.source_timestamp)

        link = self._session.scalar(
            select(CandidateObservation).where(
                CandidateObservation.candidate_id == candidate.id,
                CandidateObservation.observation_id == observation.id,
            )
        )
        if link is None:
            self._session.add(
                CandidateObservation(candidate_id=candidate.id, observation_id=observation.id)
            )
            self._session.flush()
        return candidate
