from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import CollectionBatch
from app.collectors.wikidata import WikidataClient, WikidataRawResponse
from app.models.enums import RunKind, RunStatus, Source
from app.models.tables import (
    EntityResolutionAttempt,
    EntityResolutionAttemptRawFetch,
    PipelineRun,
    RawFetch,
    SourceObservation,
    TrendCandidate,
    TrendEntity,
)
from app.pipeline.candidate import CandidateGenerator
from app.pipeline.classification import EntityClassifier
from app.pipeline.detection import TrendDetector
from app.pipeline.entity import EntityResolver, validate_live_cutoff
from app.services.collection import CollectionService


@dataclass(frozen=True)
class PipelineVersions:
    normalizer: str = "normalizer-v1"
    entity: str = "entity-v1"
    classifier: str = "classifier-v1"
    score: str = "score-v1"
    prompt: str = "prompt-v1"


def observations_for_replay(session: Session, as_of: datetime) -> Sequence[SourceObservation]:
    if as_of.tzinfo is None or as_of.utcoffset() is None or as_of.utcoffset().total_seconds() != 0:
        raise ValueError("as_of must be aware UTC")
    return list(
        session.scalars(
            select(SourceObservation)
            .where(
                SourceObservation.source_timestamp <= as_of,
                SourceObservation.observed_at <= as_of,
                SourceObservation.source != Source.WIKIDATA,
            )
            .order_by(SourceObservation.source_timestamp, SourceObservation.id)
        )
    )


class PipelineService:
    def __init__(
        self,
        session: Session,
        wikidata: WikidataClient,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._wikidata = wikidata
        self._now = now or (lambda: datetime.now(UTC))

    async def build_entities(
        self,
        as_of: datetime,
        versions: PipelineVersions | None = None,
        *,
        kind: RunKind = RunKind.LIVE,
        max_candidates: int | None = None,
        candidate_id: int | None = None,
    ) -> PipelineRun:
        if kind is RunKind.REPLAY:
            raise ValueError(
                "entity replay requires a historical entity projection; "
                "live Wikidata resolution is disabled"
            )
        versions = versions or PipelineVersions()
        started_at = self._now().astimezone(UTC)
        validate_live_cutoff(as_of, started_at)
        run = PipelineRun(
            kind=kind,
            as_of=as_of,
            started_at=started_at,
            status=RunStatus.RUNNING,
            normalizer_version=versions.normalizer,
            entity_version=versions.entity,
            classifier_version=versions.classifier,
            score_version=versions.score,
            prompt_version=versions.prompt,
        )
        self._session.add(run)
        self._session.flush()
        generator = CandidateGenerator(self._session)
        candidates: dict[int, TrendCandidate] = {}
        for observation in observations_for_replay(self._session, as_of):
            candidate = generator.generate(observation)
            candidates[candidate.id] = candidate
        resolver = EntityResolver(self._session, self._wikidata, now=lambda: started_at)
        try:
            candidates_to_resolve = list(candidates.values())
            if candidate_id is not None:
                candidates_to_resolve = [
                    candidate
                    for candidate in candidates_to_resolve
                    if candidate.id == candidate_id
                ]
            if max_candidates is not None:
                candidates_to_resolve = candidates_to_resolve[:max_candidates]
            resolved_entity_ids: set[int] = set()
            for candidate in candidates_to_resolve:
                result = await resolver.resolve(candidate, as_of)
                raw_fetch_ids: list[int] = []
                for response in result.raw_responses:
                    raw_fetch_ids.append(self._persist_wikidata_raw(response))
                attempted_at = self._now().astimezone(UTC)
                attempt = EntityResolutionAttempt(
                    candidate_id=candidate.id,
                    pipeline_run_id=run.id,
                    entity_id=result.entity_id,
                    status=result.status,
                    reason=result.reason,
                    raw_fetch_ids=raw_fetch_ids,
                    as_of=as_of,
                    attempted_at=attempted_at,
                )
                self._session.add(attempt)
                self._session.flush()
                self._session.add_all(
                    EntityResolutionAttemptRawFetch(
                        attempt_id=attempt.id, raw_fetch_id=raw_fetch_id
                    )
                    for raw_fetch_id in raw_fetch_ids
                )
                if result.entity_id is not None:
                    resolved_entity_ids.add(result.entity_id)
            classifier = EntityClassifier()
            detector = TrendDetector(
                self._session, now=self._now, score_version=versions.score
            )
            entities = []
            if resolved_entity_ids:
                entities = list(
                    self._session.scalars(
                        select(TrendEntity)
                        .where(TrendEntity.id.in_(resolved_entity_ids))
                        .order_by(TrendEntity.id)
                    )
                )
            for entity in entities:
                classifier.persist(
                    self._session,
                    entity,
                    pipeline_run_id=run.id,
                    classified_at=self._now().astimezone(UTC),
                )
                detector.snapshot(entity.id, as_of, pipeline_run_id=run.id)
        except Exception:
            run.status = RunStatus.FAILED
            run.completed_at = self._now().astimezone(UTC)
            self._session.flush()
            raise
        run.status = RunStatus.SUCCEEDED
        run.completed_at = self._now().astimezone(UTC)
        self._session.flush()
        return run

    def _persist_wikidata_raw(self, response: WikidataRawResponse) -> int:
        digest = hashlib.sha256(response.raw_bytes).hexdigest()
        url_digest = hashlib.sha256(response.request_url.encode()).hexdigest()[:16]
        batch = CollectionBatch(
            source=Source.WIKIDATA,
            collected_at=response.collected_at,
            request_url=response.request_url,
            raw_bytes=response.raw_bytes,
            items=[],
            collector_version=self._wikidata.collector_version,
            parser_version=response.parser_version,
        )
        persisted = CollectionService(self._session).persist(
            batch,
            run_key=f"wikidata:{response.collected_at:%Y%m%dT%H%M%S%fZ}:{url_digest}:{digest[:16]}",
        )
        fetch_id = self._session.scalar(
            select(RawFetch.id).where(RawFetch.run_id == persisted.run_id)
        )
        assert fetch_id is not None
        return fetch_id
