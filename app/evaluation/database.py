from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.metrics import cost, coverage, cross_source, freshness, quality
from app.evaluation.models import (
    CardFact,
    CategoryCoverage,
    CostFact,
    DailyEvaluation,
    FreshnessFact,
    SupplyMetrics,
)
from app.models.enums import (
    Category,
    HumanEvaluationLabel,
    ResolutionStatus,
    ReviewAction,
    RunKind,
    RunStatus,
    Source,
)
from app.models.tables import (
    CandidateObservation,
    Claim,
    CollectionRun,
    CostRecord,
    EntityClassification,
    EntityResolutionAttempt,
    HumanEvaluation,
    PipelineRun,
    RawPayload,
    Review,
    SourceObservation,
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
            (datetime.min.replace(tzinfo=UTC), Category.OTHER),
        )[1]
        for entity in entities
    }


def _historical_projection(session: Session, end: datetime) -> dict[int, int]:
    """Candidate-to-entity mapping as it was known before ``end``."""
    attempts = session.scalars(
        select(EntityResolutionAttempt)
        .join(PipelineRun, PipelineRun.id == EntityResolutionAttempt.pipeline_run_id)
        .where(
            EntityResolutionAttempt.as_of < end,
            EntityResolutionAttempt.attempted_at < end,
            EntityResolutionAttempt.status == ResolutionStatus.RESOLVED,
            EntityResolutionAttempt.entity_id.is_not(None),
            PipelineRun.kind == RunKind.LIVE,
            PipelineRun.status == RunStatus.SUCCEEDED,
            PipelineRun.completed_at < end,
        )
        .order_by(
            EntityResolutionAttempt.candidate_id,
            EntityResolutionAttempt.attempted_at,
            EntityResolutionAttempt.id,
        )
    )
    projection: dict[int, int] = {}
    for attempt in attempts:
        assert attempt.entity_id is not None
        projection[attempt.candidate_id] = attempt.entity_id
    reviews = session.scalars(
        select(Review)
        .where(
            Review.action.in_((ReviewAction.MERGE, ReviewAction.SPLIT)),
            Review.created_at < end,
        )
        .order_by(Review.created_at, Review.id)
    )
    for review in reviews:
        target = review.payload.get("target_entity_id")
        if not isinstance(target, int):
            continue
        if review.action is ReviewAction.MERGE:
            for candidate_id, entity_id in tuple(projection.items()):
                if entity_id == review.entity_id:
                    projection[candidate_id] = target
        else:
            for candidate_id in review.payload.get("candidate_ids", []):
                if (
                    isinstance(candidate_id, int)
                    and projection.get(candidate_id) == review.entity_id
                ):
                    projection[candidate_id] = target
    return projection


def _merge_redirects(session: Session, end: datetime) -> dict[int, int]:
    redirects: dict[int, int] = {}
    for review in session.scalars(
        select(Review)
        .where(Review.action == ReviewAction.MERGE, Review.created_at < end)
        .order_by(Review.created_at, Review.id)
    ):
        target = review.payload.get("target_entity_id")
        if not isinstance(target, int):
            continue
        for source, existing_target in tuple(redirects.items()):
            if existing_target == review.entity_id:
                redirects[source] = target
        redirects[review.entity_id] = target
    return redirects


def _source_sets(
    session: Session,
    entity_ids: set[int],
    start: datetime,
    end: datetime,
    projection: dict[int, int],
) -> dict[int, frozenset[Source]]:
    sources: defaultdict[int, set[Source]] = defaultdict(set)
    if not entity_ids:
        return {}
    rows = session.execute(
        select(CandidateObservation.candidate_id, SourceObservation.source)
        .select_from(CandidateObservation)
        .join(SourceObservation, SourceObservation.id == CandidateObservation.observation_id)
        .where(
            SourceObservation.source.in_(DISCOVERY_SOURCES),
            SourceObservation.observed_at >= start,
            SourceObservation.observed_at < end,
        )
        .distinct()
    )
    for candidate_id, source in rows:
        entity_id = projection.get(candidate_id)
        if entity_id in entity_ids:
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


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


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
    observation_rows = list(
        session.execute(
            select(SourceObservation, CandidateObservation.candidate_id)
            .join(
                CandidateObservation,
                CandidateObservation.observation_id == SourceObservation.id,
            )
            .where(
                SourceObservation.source.in_(DISCOVERY_SOURCES),
                SourceObservation.observed_at >= start,
                SourceObservation.observed_at < end,
            )
        )
    )
    observations = [row[0] for row in observation_rows]
    acquisition_candidate_ids = {row[1] for row in observation_rows}
    source_day_candidate_ids = set(
        session.scalars(
            select(CandidateObservation.candidate_id)
            .join(
                SourceObservation,
                SourceObservation.id == CandidateObservation.observation_id,
            )
            .where(
                SourceObservation.source.in_(DISCOVERY_SOURCES),
                SourceObservation.source_timestamp >= start,
                SourceObservation.source_timestamp < end,
            )
            .distinct()
        )
    )
    projection = _historical_projection(session, end)
    acquisition_entity_ids = {
        projection[candidate_id]
        for candidate_id in acquisition_candidate_ids
        if candidate_id in projection
    }
    snapshots = list(
        session.scalars(
            select(TrendSnapshot)
            .join(PipelineRun, PipelineRun.id == TrendSnapshot.pipeline_run_id)
            .where(TrendSnapshot.as_of >= start, TrendSnapshot.as_of < end)
            .where(
                PipelineRun.kind == RunKind.LIVE,
                PipelineRun.status == RunStatus.SUCCEEDED,
            )
            .order_by(TrendSnapshot.entity_id, TrendSnapshot.as_of, TrendSnapshot.id)
        )
    )
    snapshot_by_entity: dict[int, TrendSnapshot] = {}
    for snapshot in snapshots:
        snapshot_by_entity.setdefault(snapshot.entity_id, snapshot)
    merge_redirects = _merge_redirects(session, end)
    entity_ids = {
        merge_redirects.get(entity_id, entity_id) for entity_id in snapshot_by_entity
    }
    reviews_in_day = list(
        session.scalars(
            select(Review)
            .where(Review.created_at >= start, Review.created_at < end)
            .order_by(Review.created_at, Review.id)
        )
    )
    latest_reviews: dict[int, Review] = {}
    for review in session.scalars(
        select(Review)
        .where(Review.created_at < end)
        .order_by(Review.entity_id, Review.created_at, Review.id)
    ):
        latest_reviews[review.entity_id] = review
    reviewed_today = {review.entity_id for review in reviews_in_day}
    approved_ids = {
        entity_id
        for entity_id in reviewed_today
        if latest_reviews[entity_id].action is ReviewAction.APPROVE
    }
    supply = SupplyMetrics(
        raw_candidates=len(observations),
        unique_candidates=len(acquisition_entity_ids),
        trend_entities=len(entity_ids),
        approved_cards=len(approved_ids),
        source_day_candidates=len(source_day_candidate_ids),
    )

    categories = _category_by_entity(session, entity_ids | approved_ids, end)
    cards = [
        CardFact(categories.get(entity_id, Category.OTHER), entity_id in approved_ids)
        for entity_id in sorted(entity_ids | approved_ids)
    ]

    evaluation_events = list(
        session.scalars(
            select(HumanEvaluation).where(
                HumanEvaluation.created_at >= start,
                HumanEvaluation.created_at < end,
            )
            .order_by(HumanEvaluation.created_at, HumanEvaluation.id)
        )
    )
    latest_evaluations: dict[tuple[int, str], HumanEvaluation] = {}
    for evaluation in evaluation_events:
        latest_evaluations[(evaluation.entity_id, evaluation.actor)] = evaluation
    evaluations = list(latest_evaluations.values())
    claims = list(
        session.scalars(select(Claim).where(Claim.created_at >= start, Claim.created_at < end))
    )
    quality_metrics = quality(
        [evaluation.label for evaluation in evaluations],
        checked_claims=len(claims),
        blocked_claims=sum(not claim.publishable for claim in claims),
    )

    evaluation_entity_ids = {evaluation.entity_id for evaluation in evaluations}
    sources_by_entity = _source_sets(
        session,
        entity_ids | evaluation_entity_ids,
        start,
        end,
        projection,
    )
    cross_source_metrics = cross_source(
        [sources_by_entity.get(entity_id, frozenset()) for entity_id in sorted(entity_ids)]
    )

    freshness_facts: list[FreshnessFact] = []
    timing_entity_ids = entity_ids | approved_ids
    first_detection_by_entity: dict[int, datetime] = {}
    if timing_entity_ids:
        historical_snapshots = session.scalars(
            select(TrendSnapshot)
            .join(PipelineRun, PipelineRun.id == TrendSnapshot.pipeline_run_id)
            .where(
                TrendSnapshot.entity_id.in_(timing_entity_ids),
                TrendSnapshot.system_detected_at < end,
                PipelineRun.kind == RunKind.LIVE,
                PipelineRun.status == RunStatus.SUCCEEDED,
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
        observation_rows_for_detection = list(
            session.execute(
                select(SourceObservation.observed_at, CandidateObservation.candidate_id)
                .join(
                    CandidateObservation,
                    CandidateObservation.observation_id == SourceObservation.id,
                )
                .where(
                    SourceObservation.source.in_(DISCOVERY_SOURCES),
                    SourceObservation.observed_at <= detected_at,
                )
            )
        )
        detection_projection = _historical_projection(
            session, detected_at + timedelta(microseconds=1)
        )
        observation_times = [
            observed_at
            for observed_at, candidate_id in observation_rows_for_detection
            if detection_projection.get(candidate_id) == entity_id
        ]
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
    for review in reviews_in_day:
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
    if not cost_rows:
        cost_metrics = type(cost_metrics)(
            total_cost=cost_metrics.total_cost,
            human_minutes=cost_metrics.human_minutes,
            cost_per_approved_card=cost_metrics.cost_per_approved_card,
            by_type=cost_metrics.by_type,
            recorded=False,
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
    if not cost_metrics.recorded:
        missing.append("cost collection")

    category_entity_ids = entity_ids | approved_ids | evaluation_entity_ids | acquisition_entity_ids
    categories = _category_by_entity(session, category_entity_ids, end)
    base_coverage = coverage(cards)
    category_coverage: dict[Category, CategoryCoverage] = {}
    for category in Category:
        category_evaluations = [
            evaluation
            for evaluation in evaluations
            if categories.get(evaluation.entity_id, Category.OTHER) is category
        ]
        category_labels = [evaluation.label for evaluation in category_evaluations]
        reviewed = len(category_labels)
        duplicates = category_labels.count(HumanEvaluationLabel.DUPLICATE)
        news_only = category_labels.count(HumanEvaluationLabel.NEWS_ONLY)
        noise = sum(
            category_labels.count(label)
            for label in (
                HumanEvaluationLabel.TOO_OBVIOUS,
                HumanEvaluationLabel.NEWS_ONLY,
                HumanEvaluationLabel.NOT_USEFUL,
            )
        )
        raw_count = sum(
            categories.get(projection.get(candidate_id, -1), Category.OTHER) is category
            for _, candidate_id in observation_rows
        )
        base = base_coverage[category]
        category_coverage[category] = CategoryCoverage(
            candidates=sum(
                categories.get(entity_id, Category.OTHER) is category
                for entity_id in acquisition_entity_ids
            ),
            valid_cards=base.valid_cards,
            raw_candidates=raw_count,
            reviewed=reviewed,
            usable_cards=category_labels.count(HumanEvaluationLabel.VALID_TREND),
            duplicate_items=duplicates,
            noise_items=noise,
            news_only_items=news_only,
            usable_rate=_rate(
                category_labels.count(HumanEvaluationLabel.VALID_TREND), reviewed
            ),
            duplicate_rate=_rate(duplicates, reviewed),
            noise_rate=_rate(noise, reviewed),
            news_only_rate=_rate(news_only, reviewed),
        )

    return DailyEvaluation(
        day=day,
        complete_day=set(DISCOVERY_SOURCES).issubset(completed_sources),
        supply=supply,
        coverage=category_coverage,
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
