from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ResolutionStatus, RunKind, RunStatus
from app.models.tables import EntityResolutionAttempt, PipelineRun, TrendSnapshot
from app.pipeline.detection import TrendDetector
from app.services.pipeline import PipelineVersions


class InvalidReplayRange(ValueError):
    pass


class ReplayVersionConflict(ValueError):
    pass


@dataclass(frozen=True)
class ReplayResult:
    run_id: int | None
    snapshot_count: int
    snapshot_digest: str
    entity_ids: tuple[int, ...]
    dry_run: bool


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
    def __init__(
        self, session: Session, *, now: Callable[[], datetime] | None = None
    ) -> None:
        self._session = session
        self._now = now or (lambda: datetime.now(UTC))

    def run(
        self,
        from_: datetime,
        to: datetime,
        *,
        score_version: str,
        dry_run: bool = False,
    ) -> ReplayResult:
        _validate_range(from_, to)
        if not score_version.strip():
            raise ValueError("score_version must be non-empty")
        now = self._now().astimezone(UTC)
        versions = PipelineVersions(score=score_version)
        run: PipelineRun | None = None
        if not dry_run:
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

        projections = self._historical_projection(to)
        detector = TrendDetector(
            self._session, now=lambda: now, score_version=score_version
        )
        snapshots: list[TrendSnapshot] = []
        for entity_id, candidate_ids in sorted(projections.items()):
            snapshot = detector.replay_snapshot(
                entity_id,
                tuple(sorted(candidate_ids)),
                to,
                from_=from_,
                pipeline_run_id=run.id if run is not None else 0,
                persist=not dry_run,
            )
            if snapshot is not None:
                if run is not None and snapshot.pipeline_run_id != run.id:
                    raise ReplayVersionConflict(
                        "a snapshot already exists for this cutoff and score version; "
                        "persist replay output with a new score_version"
                    )
                snapshots.append(snapshot)
        digest = _snapshot_digest(from_, to, score_version, snapshots)
        if run is not None:
            run.snapshot_digest = digest
            run.status = RunStatus.SUCCEEDED
            run.completed_at = self._now().astimezone(UTC)
            self._session.flush()
        return ReplayResult(
            run_id=run.id if run is not None else None,
            snapshot_count=len(snapshots),
            snapshot_digest=digest,
            entity_ids=tuple(sorted(snapshot.entity_id for snapshot in snapshots)),
            dry_run=dry_run,
        )

    def _historical_projection(self, to: datetime) -> dict[int, set[int]]:
        attempts = self._session.scalars(
            select(EntityResolutionAttempt)
            .join(PipelineRun, PipelineRun.id == EntityResolutionAttempt.pipeline_run_id)
            .where(
                EntityResolutionAttempt.as_of <= to,
                EntityResolutionAttempt.status == ResolutionStatus.RESOLVED,
                EntityResolutionAttempt.entity_id.is_not(None),
                PipelineRun.kind == RunKind.LIVE,
                PipelineRun.status == RunStatus.SUCCEEDED,
            )
            .order_by(
                EntityResolutionAttempt.candidate_id,
                EntityResolutionAttempt.as_of,
                EntityResolutionAttempt.id,
            )
        )
        latest_by_candidate: dict[int, EntityResolutionAttempt] = {}
        for attempt in attempts:
            latest_by_candidate[attempt.candidate_id] = attempt
        projection: defaultdict[int, set[int]] = defaultdict(set)
        for candidate_id, attempt in latest_by_candidate.items():
            assert attempt.entity_id is not None
            projection[attempt.entity_id].add(candidate_id)
        return dict(projection)


def _snapshot_digest(
    from_: datetime,
    to: datetime,
    score_version: str,
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
        for snapshot in sorted(snapshots, key=lambda item: item.entity_id)
    ]
    canonical = json.dumps(
        {
            "from": from_.isoformat(),
            "to": to.isoformat(),
            "score_version": score_version,
            "snapshots": rows,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
