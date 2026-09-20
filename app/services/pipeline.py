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
from app.models.tables import PipelineRun, SourceObservation, TrendCandidate
from app.pipeline.candidate import CandidateGenerator
from app.pipeline.entity import EntityResolver
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
    ) -> PipelineRun:
        versions = versions or PipelineVersions()
        started_at = self._now().astimezone(UTC)
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
        resolver = EntityResolver(self._session, self._wikidata)
        try:
            candidates_to_resolve = list(candidates.values())
            if max_candidates is not None:
                candidates_to_resolve = candidates_to_resolve[:max_candidates]
            for candidate in candidates_to_resolve:
                result = await resolver.resolve(candidate, as_of)
                for response in result.raw_responses:
                    self._persist_wikidata_raw(response)
        except Exception:
            run.status = RunStatus.FAILED
            run.completed_at = self._now().astimezone(UTC)
            self._session.flush()
            raise
        run.status = RunStatus.SUCCEEDED
        run.completed_at = self._now().astimezone(UTC)
        self._session.flush()
        return run

    def _persist_wikidata_raw(self, response: WikidataRawResponse) -> None:
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
        CollectionService(self._session).persist(
            batch,
            run_key=f"wikidata:{response.collected_at:%Y%m%dT%H%M%S%fZ}:{url_digest}:{digest[:16]}",
        )
