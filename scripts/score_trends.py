from __future__ import annotations

import argparse
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import session_scope
from app.models.enums import ResolutionStatus, RunKind, RunStatus
from app.models.tables import PipelineRun, TrendEntity
from app.pipeline.detection import TrendDetector
from app.services.pipeline import PipelineVersions
from scripts.collect import parse_as_of


def score(as_of_text: str | None) -> None:
    as_of = parse_as_of(as_of_text)
    now = datetime.now(UTC)
    versions = PipelineVersions()
    with session_scope() as session:
        run = PipelineRun(
            kind=RunKind.LIVE,
            as_of=as_of,
            started_at=now,
            status=RunStatus.RUNNING,
            normalizer_version=versions.normalizer,
            entity_version=versions.entity,
            classifier_version=versions.classifier,
            score_version=versions.score,
            prompt_version=versions.prompt,
        )
        session.add(run)
        session.flush()
        detector = TrendDetector(session, score_version=versions.score)
        created = []
        entities = session.scalars(
            select(TrendEntity)
            .where(TrendEntity.resolution_status == ResolutionStatus.RESOLVED)
            .order_by(TrendEntity.id)
        )
        for entity in entities:
            snapshot = detector.snapshot(entity.id, as_of, pipeline_run_id=run.id)
            if snapshot is not None:
                created.append(snapshot)
        run.status = RunStatus.SUCCEEDED
        run.completed_at = datetime.now(UTC)
        session.flush()
        print(
            f"pipeline_run={run.id} status={run.status.value} "
            f"entities={len(created)} as_of={as_of.isoformat()}"
        )
        for snapshot in created:
            print(
                f"entity={snapshot.entity_id} lifecycle={snapshot.lifecycle.value} "
                f"trend_score={snapshot.total_score:.2f}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Score resolved trend entities")
    parser.add_argument("--as-of")
    args = parser.parse_args()
    score(args.as_of)


if __name__ == "__main__":
    main()
