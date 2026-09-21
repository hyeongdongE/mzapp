from __future__ import annotations

import base64
import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import SourceItem
from app.collectors.google_trends import parse_google_trends_rss
from app.collectors.wikimedia import parse_wikimedia_top_pages
from app.models.enums import ResolutionStatus, RunKind, RunStatus, Source
from app.models.tables import (
    EntityResolutionAttempt,
    PipelineRun,
    RawFetch,
    RawPayload,
    TrendCandidate,
    TrendSnapshot,
)
from app.pipeline.baseline import SignalPoint
from app.pipeline.detection import BASELINE_LOOKBACK, TrendDetector
from app.pipeline.normalization import normalize_text
from app.services.pipeline import PipelineVersions


class InvalidReplayRange(ValueError):
    pass


class ReplayVersionConflict(ValueError):
    pass


class InvalidRawPayload(ValueError):
    pass


@dataclass(frozen=True)
class ReplayResult:
    run_id: int | None
    snapshot_count: int
    snapshot_digest: str
    entity_ids: tuple[int, ...]
    dry_run: bool


@dataclass(frozen=True)
class _ReplayInput:
    candidate_id: int
    point: SignalPoint


@dataclass(frozen=True, order=True)
class _RawProvenance:
    source: str
    raw_fetch_id: int
    request_url: str
    collected_at: str
    source_timestamp: str | None
    collector_version: str
    parser_version: str
    payload_hash: str


def _validate_range(from_: datetime, to: datetime) -> None:
    for name, value in (("from_", from_), ("to", to)):
        if (
            value.tzinfo is None
            or value.utcoffset() is None
            or value.utcoffset().total_seconds() != 0
        ):
            raise InvalidReplayRange(f"{name} must be aware UTC")
    if from_ > to:
        raise InvalidReplayRange("from_ must be at or before to")


class ReplayService:
    """Rebuild score history from immutable official raw payloads."""

    def __init__(self, session: Session, *, now: Callable[[], datetime] | None = None) -> None:
        self._session = session
        self._now = now or (lambda: datetime.now(UTC))

    def run(
        self,
        from_: datetime,
        to: datetime,
        *,
        score_version: str,
        normalizer_version: str = "normalizer-v1",
        entity_version: str = "entity-v1",
        classifier_version: str = "classifier-v2",
        prompt_version: str = "prompt-v1",
        dry_run: bool = False,
    ) -> ReplayResult:
        _validate_range(from_, to)
        versions = PipelineVersions(
            normalizer=normalizer_version,
            entity=entity_version,
            classifier=classifier_version,
            score=score_version,
            prompt=prompt_version,
        )
        if any(not value.strip() for value in asdict(versions).values()):
            raise ValueError("replay versions must be non-empty")
        supported = PipelineVersions(score=score_version)
        for field in ("normalizer", "entity", "classifier", "prompt"):
            if getattr(versions, field) != getattr(supported, field):
                raise ValueError(
                    f"unsupported {field}_version {getattr(versions, field)!r}; "
                    f"only {getattr(supported, field)!r} is implemented"
                )

        raw_provenance, replay_inputs = self._reparse_inputs(
            from_ - BASELINE_LOOKBACK, to
        )
        transaction = self._session.begin_nested() if dry_run else None
        try:
            result = self._execute(from_, to, versions, raw_provenance, replay_inputs, dry_run)
            if transaction is not None:
                transaction.rollback()
            return result
        except Exception:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
            raise

    def _execute(
        self,
        from_: datetime,
        to: datetime,
        versions: PipelineVersions,
        raw_provenance: tuple[_RawProvenance, ...],
        replay_inputs: list[_ReplayInput],
        dry_run: bool,
    ) -> ReplayResult:
        now = self._now().astimezone(UTC)
        run = PipelineRun(
            kind=RunKind.REPLAY,
            as_of=to,
            started_at=now,
            status=RunStatus.RUNNING,
            normalizer_version=versions.normalizer,
            entity_version=versions.entity,
            classifier_version=versions.classifier,
            score_version=versions.score,
            prompt_version=versions.prompt,
        )
        self._session.add(run)
        self._session.flush()

        detector = TrendDetector(self._session, now=lambda: now, score_version=versions.score)
        snapshots: list[TrendSnapshot] = []
        for cutoff in _cutoffs(from_, to):
            candidate_to_entity = self._historical_projection(cutoff)
            grouped: defaultdict[int, list[SignalPoint]] = defaultdict(list)
            candidates_by_entity: defaultdict[int, set[int]] = defaultdict(set)
            for replay_input in replay_inputs:
                if replay_input.point.observed_at > cutoff:
                    continue
                entity_id = candidate_to_entity.get(replay_input.candidate_id)
                if entity_id is None:
                    continue
                grouped[entity_id].append(replay_input.point)
                candidates_by_entity[entity_id].add(replay_input.candidate_id)
            for entity_id in sorted(grouped):
                snapshot = detector.replay_snapshot(
                    entity_id,
                    tuple(sorted(candidates_by_entity[entity_id])),
                    cutoff,
                    from_=from_,
                    pipeline_run_id=run.id,
                    persist=True,
                    points=grouped[entity_id],
                    history_pipeline_run_id=run.id,
                )
                if snapshot is None:
                    continue
                if snapshot.pipeline_run_id != run.id:
                    raise ReplayVersionConflict(
                        "a snapshot already exists for this cutoff and score version; "
                        "persist replay output with a new score_version"
                    )
                snapshots.append(snapshot)

        digest = _snapshot_digest(from_, to, versions, raw_provenance, snapshots)
        entity_ids = tuple(sorted({snapshot.entity_id for snapshot in snapshots}))
        snapshot_count = len(snapshots)
        run.snapshot_digest = digest
        run.status = RunStatus.SUCCEEDED
        run.completed_at = self._now().astimezone(UTC)
        self._session.flush()
        return ReplayResult(
            run_id=None if dry_run else run.id,
            snapshot_count=snapshot_count,
            snapshot_digest=digest,
            entity_ids=entity_ids,
            dry_run=dry_run,
        )

    def _reparse_inputs(
        self, from_: datetime, to: datetime
    ) -> tuple[tuple[_RawProvenance, ...], list[_ReplayInput]]:
        rows = self._session.execute(
            select(RawFetch, RawPayload)
            .join(RawPayload, RawPayload.id == RawFetch.raw_payload_id)
            .where(
                RawPayload.source.in_((Source.GOOGLE_TRENDS, Source.WIKIMEDIA)),
                RawFetch.collected_at >= from_,
                RawFetch.collected_at <= to,
            )
            .order_by(RawFetch.collected_at, RawFetch.id)
        )
        candidate_index: dict[tuple[Source, str], TrendCandidate] = {}
        for candidate in self._session.scalars(
            select(TrendCandidate)
            .where(TrendCandidate.first_seen_at <= to)
            .order_by(TrendCandidate.generation, TrendCandidate.id)
        ):
            candidate_index[(candidate.source, candidate.normalized_text)] = candidate

        raw_provenance: list[_RawProvenance] = []
        result: list[_ReplayInput] = []
        for raw_fetch, payload in rows:
            raw_bytes = _raw_bytes(payload)
            digest = hashlib.sha256(raw_bytes).hexdigest()
            if digest != payload.payload_hash:
                raise InvalidRawPayload(f"raw payload hash mismatch for payload {payload.id}")
            raw_provenance.append(
                _RawProvenance(
                    source=payload.source.value,
                    raw_fetch_id=raw_fetch.id,
                    request_url=raw_fetch.request_url,
                    collected_at=_utc(raw_fetch.collected_at).isoformat(),
                    source_timestamp=(
                        _utc(raw_fetch.source_timestamp).isoformat()
                        if raw_fetch.source_timestamp is not None
                        else None
                    ),
                    collector_version=raw_fetch.collector_version,
                    parser_version=raw_fetch.parser_version,
                    payload_hash=digest,
                )
            )
            for item in _parse_payload(payload.source, raw_bytes, raw_fetch):
                normalized = normalize_text(item.canonical_text)
                candidate = candidate_index.get((payload.source, normalized))
                if candidate is None:
                    raise InvalidRawPayload(
                        "parsed replay item has no normalized candidate: "
                        f"{payload.source.value}/{normalized}"
                    )
                point = _to_point(item, candidate.id, normalized, payload.source)
                result.append(_ReplayInput(candidate.id, point))
        return tuple(sorted(raw_provenance)), result

    def _historical_projection(self, cutoff: datetime) -> dict[int, int]:
        attempts = self._session.scalars(
            select(EntityResolutionAttempt)
            .join(PipelineRun, PipelineRun.id == EntityResolutionAttempt.pipeline_run_id)
            .where(
                EntityResolutionAttempt.as_of <= cutoff,
                EntityResolutionAttempt.status == ResolutionStatus.RESOLVED,
                EntityResolutionAttempt.entity_id.is_not(None),
                PipelineRun.kind == RunKind.LIVE,
                PipelineRun.status == RunStatus.SUCCEEDED,
                PipelineRun.completed_at <= cutoff,
            )
            .order_by(
                EntityResolutionAttempt.candidate_id,
                EntityResolutionAttempt.as_of,
                EntityResolutionAttempt.id,
            )
        )
        latest: dict[int, int] = {}
        for attempt in attempts:
            assert attempt.entity_id is not None
            latest[attempt.candidate_id] = attempt.entity_id
        return latest


def _cutoffs(from_: datetime, to: datetime) -> tuple[datetime, ...]:
    values: list[datetime] = []
    current = from_
    while current <= to:
        values.append(current)
        current += timedelta(hours=6)
    if not values or values[-1] != to:
        values.append(to)
    return tuple(values)


def _raw_bytes(payload: RawPayload) -> bytes:
    value = payload.raw_payload
    if value.get("content_encoding") != "base64" or not isinstance(value.get("data"), str):
        raise InvalidRawPayload(f"raw payload {payload.id} is not canonical base64")
    try:
        return base64.b64decode(value["data"], validate=True)
    except ValueError as exc:
        raise InvalidRawPayload(f"raw payload {payload.id} has invalid base64") from exc


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_payload(source: Source, raw_bytes: bytes, raw_fetch: RawFetch) -> list[SourceItem]:
    observed_at = _utc(raw_fetch.collected_at)
    if source is Source.GOOGLE_TRENDS:
        if raw_fetch.parser_version != "google-rss-parser-v1":
            raise InvalidRawPayload(f"unsupported Google parser version {raw_fetch.parser_version}")
        return parse_google_trends_rss(raw_bytes, observed_at, raw_fetch.request_url)
    if source is Source.WIKIMEDIA:
        if raw_fetch.parser_version != "wikimedia-top-per-country-parser-v1":
            raise InvalidRawPayload(
                f"unsupported Wikimedia parser version {raw_fetch.parser_version}"
            )
        return parse_wikimedia_top_pages(raw_bytes, observed_at, raw_fetch.request_url)
    raise InvalidRawPayload(f"unsupported replay source {source.value}")


def _to_point(item: SourceItem, candidate_id: int, normalized: str, source: Source) -> SignalPoint:
    metric: float | None = None
    rank: int | None = None
    news_count = 0
    raw_metric = item.metrics.get("approx_traffic_lower_bound")
    if isinstance(raw_metric, (int, float)) and not isinstance(raw_metric, bool):
        metric = float(raw_metric)
    views = item.metrics.get("views_ceil")
    if metric is None and isinstance(views, (int, float)) and not isinstance(views, bool):
        metric = float(views)
    raw_rank = item.metrics.get("rank")
    if isinstance(raw_rank, int) and not isinstance(raw_rank, bool):
        rank = raw_rank
    news = item.metrics.get("news_items")
    if isinstance(news, list):
        news_count = len(news)
    return SignalPoint(
        source=source,
        source_timestamp=item.source_timestamp.astimezone(UTC),
        observed_at=item.observed_at.astimezone(UTC),
        normalized_text=normalized,
        metric=metric,
        rank=rank,
        news_count=news_count,
        candidate_id=candidate_id,
        source_item_key=item.source_item_id,
    )


def _snapshot_digest(
    from_: datetime,
    to: datetime,
    versions: PipelineVersions,
    raw_provenance: tuple[_RawProvenance, ...],
    snapshots: list[TrendSnapshot],
) -> str:
    rows = [
        {
            "entity_id": snapshot.entity_id,
            "as_of": snapshot.as_of.astimezone(UTC).isoformat(),
            "lifecycle": snapshot.lifecycle.value,
            "total_score": snapshot.total_score,
            "breakdown": snapshot.breakdown,
            "missing_inputs": snapshot.missing_inputs,
        }
        for snapshot in sorted(snapshots, key=lambda item: (item.as_of, item.entity_id))
    ]
    canonical = json.dumps(
        {
            "from": from_.isoformat(),
            "to": to.isoformat(),
            "versions": asdict(versions),
            "raw_payloads": [asdict(item) for item in raw_provenance],
            "snapshots": rows,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
