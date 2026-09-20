from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.metrics import cost, coverage, cross_source, freshness, quality
from app.evaluation.models import (
    CardFact,
    CostFact,
    DailyEvaluation,
    FreshnessFact,
    SupplyMetrics,
)
from app.models.enums import (
    Category,
    HumanEvaluationLabel,
    ReviewAction,
    RunStatus,
    Source,
)
from app.models.tables import (
    CandidateObservation,
    Claim,
    CollectionRun,
    CostRecord,
    EntityCandidate,
    EntityClassification,
    HumanEvaluation,
    PipelineRun,
    RawPayload,
    Review,
    SourceObservation,
    TrendCandidate,
    TrendEntity,
    TrendSnapshot,
)

DISCOVERY_SOURCES = (Source.GOOGLE_TRENDS, Source.WIKIMEDIA)
VERSION_KEYS = (
    "collector",
    "parser",
    "normalizer",
    "entity",
    "classifier",
    "score",
    "prompt",
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _category_by_entity(
    session: Session, entity_ids: set[int], end: datetime
) -> dict[int, Category]:
    if not entity_ids:
        return {}
    selected: dict[int, tuple[datetime, Category]] = {}
    classifications = session.scalars(
        select(EntityClassification)
        .where(
            EntityClassification.entity_id.in_(entity_ids),
            EntityClassification.classified_at < end,
        )
        .order_by(EntityClassification.classified_at, EntityClassification.id)
    )
    for item in classifications:
        selected[item.entity_id] = (_utc(item.classified_at), item.category)
    category_reviews = session.scalars(
        select(Review)
        .where(
            Review.entity_id.in_(entity_ids),
            Review.action == ReviewAction.CHANGE_CATEGORY,
            Review.created_at < end,
        )
        .order_by(Review.created_at, Review.id)
    )
    for review in category_reviews:
        raw_category = review.payload.get("category")
        try:
            reviewed_category = Category(raw_category)
        except (TypeError, ValueError):
            continue
        timestamp = _utc(review.created_at)
        previous = selected.get(review.entity_id)
        if previous is None or timestamp >= previous[0]:
            selected[review.entity_id] = (timestamp, reviewed_category)
    entities = session.scalars(select(TrendEntity).where(TrendEntity.id.in_(entity_ids)))
    return {
        entity.id: selected.get(
            entity.id,
            (datetime.min.replace(tzinfo=UTC), entity.category or Category.OTHER),
        )[1]
        for entity in entities
    }


def _source_sets(
    session: Session, entity_ids: set[int], end: datetime
) -> dict[int, frozenset[Source]]:
    sources: defaultdict[int, set[Source]] = defaultdict(set)
    if not entity_ids:
        return {}
    rows = session.execute(
        select(EntityCandidate.entity_id, SourceObservation.source)
        .join(
            CandidateObservation,
            CandidateObservation.candidate_id == EntityCandidate.candidate_id,
        )
        .join(SourceObservation, SourceObservation.id == CandidateObservation.observation_id)
        .where(
            EntityCandidate.entity_id.in_(entity_ids),
            SourceObservation.source.in_(DISCOVERY_SOURCES),
            SourceObservation.source_timestamp < end,
            SourceObservation.observed_at < end,
        )
        .distinct()
    )
    for entity_id, source in rows:
        sources[entity_id].add(source)
    return {entity_id: frozenset(values) for entity_id, values in sources.items()}


def _versions(session: Session, start: datetime, end: datetime) -> dict[str, tuple[str, ...]]:
    values: dict[str, set[str]] = {key: set() for key in VERSION_KEYS}
    payloads = session.scalars(
        select(RawPayload).where(
            RawPayload.collected_at >= start,
            RawPayload.collected_at < end,
        )
    )
    for payload in payloads:
        values["collector"].add(payload.collector_version)
        values["parser"].add(payload.parser_version)
    runs = session.scalars(
        select(PipelineRun).where(PipelineRun.as_of >= start, PipelineRun.as_of < end)
    )
    for run in runs:
        values["normalizer"].add(run.normalizer_version)
        values["entity"].add(run.entity_version)
        values["classifier"].add(run.classifier_version)
        values["score"].add(run.score_version)
        values["prompt"].add(run.prompt_version)
    return {key: tuple(sorted(values[key])) for key in VERSION_KEYS}


def _hourly_rate(record: CostRecord) -> Decimal:
    raw = record.metadata_json.get("hourly_rate", "0")
    try:
        return Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError(f"invalid hourly_rate on cost record {record.id}") from exc


def evaluate_day(session: Session, day: date) -> DailyEvaluation:
    start, end = _window(day)
    completed_sources = set(
        session.scalars(
            select(CollectionRun.source).where(
                CollectionRun.source.in_(DISCOVERY_SOURCES),
                CollectionRun.status == RunStatus.SUCCEEDED,
                CollectionRun.started_at >= start,
                CollectionRun.started_at < end,
            )
        )
    )
    observations = list(
        session.scalars(
            select(SourceObservation).where(
                SourceObservation.source.in_(DISCOVERY_SOURCES),
                SourceObservation.observed_at >= start,
                SourceObservation.observed_at < end,
            )
        )
    )
    candidates = list(
        session.scalars(
            select(TrendCandidate).where(
                TrendCandidate.first_seen_at >= start,
                TrendCandidate.first_seen_at < end,
            )
        )
    )
    snapshots = list(
        session.scalars(
            select(TrendSnapshot)
            .where(TrendSnapshot.as_of >= start, TrendSnapshot.as_of < end)
            .order_by(TrendSnapshot.entity_id, TrendSnapshot.as_of, TrendSnapshot.id)
        )
    )
    snapshot_by_entity: dict[int, TrendSnapshot] = {}
    for snapshot in snapshots:
        snapshot_by_entity.setdefault(snapshot.entity_id, snapshot)
    entity_ids = set(snapshot_by_entity)
    reviews = list(
        session.scalars(
            select(Review)
            .where(Review.created_at >= start, Review.created_at < end)
            .order_by(Review.created_at, Review.id)
        )
    )
    approved_ids = {review.entity_id for review in reviews if review.action is ReviewAction.APPROVE}
    supply = SupplyMetrics(
        raw_candidates=len(observations),
        unique_candidates=len(candidates),
        trend_entities=len(entity_ids),
        approved_cards=len(approved_ids),
    )

    categories = _category_by_entity(session, entity_ids | approved_ids, end)
    cards = [
        CardFact(categories.get(entity_id, Category.OTHER), entity_id in approved_ids)
        for entity_id in sorted(entity_ids | approved_ids)
    ]

    evaluations = list(
        session.scalars(
            select(HumanEvaluation).where(
                HumanEvaluation.created_at >= start,
                HumanEvaluation.created_at < end,
            )
        )
    )
    claims = list(
        session.scalars(
            select(Claim).where(Claim.created_at >= start, Claim.created_at < end)
        )
    )
    quality_metrics = quality(
        [evaluation.label for evaluation in evaluations],
        checked_claims=len(claims),
        blocked_claims=sum(not claim.publishable for claim in claims),
    )

    evaluation_entity_ids = {evaluation.entity_id for evaluation in evaluations}
    sources_by_entity = _source_sets(session, entity_ids | evaluation_entity_ids, end)
    cross_source_metrics = cross_source(
        [sources_by_entity.get(entity_id, frozenset()) for entity_id in sorted(entity_ids)]
    )

    freshness_facts: list[FreshnessFact] = []
    timing_entity_ids = entity_ids | approved_ids
    first_detection_by_entity: dict[int, datetime] = {}
    if timing_entity_ids:
        historical_snapshots = session.scalars(
            select(TrendSnapshot)
            .where(
                TrendSnapshot.entity_id.in_(timing_entity_ids),
                TrendSnapshot.system_detected_at < end,
            )
            .order_by(
                TrendSnapshot.entity_id,
                TrendSnapshot.system_detected_at,
                TrendSnapshot.id,
            )
        )
        for snapshot in historical_snapshots:
            first_detection_by_entity.setdefault(
                snapshot.entity_id, _utc(snapshot.system_detected_at)
            )

    for entity_id, detected_at in first_detection_by_entity.items():
        if not start <= detected_at < end:
            continue
        observation_times = list(
            session.scalars(
                select(SourceObservation.observed_at)
                .join(
                    CandidateObservation,
                    CandidateObservation.observation_id == SourceObservation.id,
                )
                .join(
                    EntityCandidate,
                    EntityCandidate.candidate_id == CandidateObservation.candidate_id,
                )
                .where(
                    EntityCandidate.entity_id == entity_id,
                    SourceObservation.source.in_(DISCOVERY_SOURCES),
                    SourceObservation.observed_at <= detected_at,
                )
            )
        )
        if not observation_times:
            continue
        first_seen = min(_utc(value) for value in observation_times)
        freshness_facts.append(
            FreshnessFact(
                detection_delay=detected_at - first_seen,
                approval_delay=None,
            )
        )
    first_approval_by_entity: dict[int, datetime] = {}
    for review in reviews:
        if review.action is not ReviewAction.APPROVE:
            continue
        first_approval_by_entity.setdefault(review.entity_id, _utc(review.created_at))
    for entity_id, approved_at in first_approval_by_entity.items():
        detected_at = first_detection_by_entity.get(entity_id)
        if detected_at is None:
            continue
        freshness_facts.append(
            FreshnessFact(
                detection_delay=None,
                approval_delay=approved_at - detected_at,
            )
        )
    freshness_metrics = freshness(freshness_facts)

    cost_rows = list(
        session.scalars(
            select(CostRecord).where(
                CostRecord.recorded_at >= start,
                CostRecord.recorded_at < end,
            )
        )
    )
    if any(record.currency != "USD" for record in cost_rows):
        raise ValueError("evaluation cannot aggregate mixed or non-USD cost records")
    cost_metrics = cost(
        [
            CostFact(
                cost_type=record.cost_type,
                amount=Decimal(record.amount),
                human_minutes=record.human_minutes,
                hourly_rate=_hourly_rate(record),
            )
            for record in cost_rows
        ],
        approved=supply.approved_cards,
    )

    noise_sources: Counter[str] = Counter()
    for evaluation in evaluations:
        if evaluation.label is HumanEvaluationLabel.VALID_TREND:
            continue
        for source in sources_by_entity.get(evaluation.entity_id, frozenset()):
            noise_sources[source.value] += 1

    missing: list[str] = []
    if quality_metrics.reviewed == 0:
        missing.append("human evaluation quality")
    if quality_metrics.checked_claims == 0:
        missing.append("summary support quality")
    if cross_source_metrics.eligible_entities == 0:
        missing.append("cross-source confirmation")
    if freshness_metrics.detection_samples == 0:
        missing.append("detection freshness")
    if freshness_metrics.approval_samples == 0:
        missing.append("approval freshness")
    if supply.approved_cards == 0:
        missing.append("cost per approved card")

    return DailyEvaluation(
        day=day,
        complete_day=set(DISCOVERY_SOURCES).issubset(completed_sources),
        supply=supply,
        coverage=coverage(cards),
        quality=quality_metrics,
        cross_source=cross_source_metrics,
        freshness=freshness_metrics,
        cost=cost_metrics,
        top_noise_sources=tuple(
            sorted(noise_sources.items(), key=lambda item: (-item[1], item[0]))[:5]
        ),
        versions=_versions(session, start, end),
        decision="CONTINUE_DATA_COLLECTION",
        missing_denominators=tuple(missing),
    )
