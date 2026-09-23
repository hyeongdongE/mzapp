from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.enums import (
    BriefItemUsefulness,
    BriefReviewSessionStatus,
    BriefStatus,
    CandidateStatus,
    Category,
    CategoryAvailability,
    ClusterStatus,
    DataMode,
    DuplicateEscapeVerdict,
    EventSelectionVerdict,
    EvidenceConfidence,
    EvidenceKind,
    EvidenceSetUsefulness,
    EvidenceStatus,
    FactCorrectness,
    FeedbackType,
    HumanEvaluationLabel,
    IncorrectMergeVerdict,
    InterpretationQuality,
    MissingEventDiscoverySource,
    NotificationMode,
    ProductEventType,
    ResolutionStatus,
    ReviewAction,
    ReviewStatus,
    RunKind,
    RunStatus,
    Source,
    TrendLifecycle,
    VerbosityVerdict,
    WatchUsefulness,
)


def enum_column(enum_type: type[Any]) -> SqlEnum:
    return SqlEnum(enum_type, native_enum=False, length=64)


class Base(DeclarativeBase):
    pass


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    source: Mapped[Source] = mapped_column(enum_column(Source), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RunStatus] = mapped_column(enum_column(RunStatus), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))


class RawPayload(Base):
    __tablename__ = "raw_payloads"
    __table_args__ = (UniqueConstraint("source", "payload_hash", name="uq_raw_source_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[Source] = mapped_column(enum_column(Source), nullable=False, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collector_version: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)


class RawFetch(Base):
    __tablename__ = "raw_fetches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("collection_runs.id"), unique=True, nullable=False
    )
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw_payloads.id"), nullable=False)
    request_url: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collector_version: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)


class SourceObservation(Base):
    __tablename__ = "source_observations"
    __table_args__ = (
        UniqueConstraint("run_id", "source_item_id", name="uq_observation_run_item"),
        Index("ix_observation_source_time", "source", "source_timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id"), nullable=False)
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw_payloads.id"), nullable=False)
    source: Mapped[Source] = mapped_column(enum_column(Source), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(240), nullable=False)
    canonical_text: Mapped[str] = mapped_column(String(500), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[RunKind] = mapped_column(enum_column(RunKind), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RunStatus] = mapped_column(enum_column(RunStatus), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_version: Mapped[str] = mapped_column(String(80), nullable=False)
    classifier_version: Mapped[str] = mapped_column(String(80), nullable=False)
    score_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_digest: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(120))


class TrendCandidate(Base):
    __tablename__ = "trend_candidates"
    __table_args__ = (
        UniqueConstraint(
            "source", "normalized_text", "generation", name="uq_candidate_source_text_generation"
        ),
        Index("ix_candidate_status_seen", "status", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[Source] = mapped_column(enum_column(Source), nullable=False)
    canonical_text: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(500), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[CandidateStatus] = mapped_column(enum_column(CandidateStatus), nullable=False)
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        enum_column(ResolutionStatus), nullable=False, default=ResolutionStatus.NEEDS_REVIEW
    )
    normalizer_version: Mapped[str] = mapped_column(String(80), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CandidateObservation(Base):
    __tablename__ = "candidate_observations"
    __table_args__ = (
        UniqueConstraint("candidate_id", "observation_id", name="uq_candidate_observation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("trend_candidates.id"), nullable=False)
    observation_id: Mapped[int] = mapped_column(
        ForeignKey("source_observations.id"), nullable=False
    )


class TrendEntity(Base):
    __tablename__ = "trend_entities"
    __table_args__ = (Index("ix_entity_category_review", "category", "review_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    wikidata_id: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        enum_column(ResolutionStatus), nullable=False
    )
    entity_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    category: Mapped[Category | None] = mapped_column(enum_column(Category), index=True)
    review_status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus), nullable=False, default=ReviewStatus.PENDING
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint("entity_id", "normalized_alias", "language", name="uq_entity_alias"),
        Index("ix_alias_normalized", "normalized_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("trend_entities.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="und")
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="WIKIDATA_ALIAS")
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class EntityCandidate(Base):
    __tablename__ = "entity_candidates"
    __table_args__ = (
        UniqueConstraint("entity_id", "candidate_id", name="uq_entity_candidate"),
        UniqueConstraint("candidate_id", name="uq_entity_candidate_single_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("trend_entities.id"), nullable=False)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("trend_candidates.id"), nullable=False)
    entity_version: Mapped[str] = mapped_column(String(80), nullable=False)
    match_reason: Mapped[str] = mapped_column(String(160), nullable=False)


class EntityResolutionAttempt(Base):
    __tablename__ = "entity_resolution_attempts"
    __table_args__ = (
        Index("ix_resolution_attempt_run_candidate", "pipeline_run_id", "candidate_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("trend_candidates.id"), nullable=False)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("trend_entities.id"))
    status: Mapped[ResolutionStatus] = mapped_column(
        enum_column(ResolutionStatus), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(160), nullable=False)
    raw_fetch_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntityResolutionAttemptRawFetch(Base):
    __tablename__ = "entity_resolution_attempt_raw_fetches"
    __table_args__ = (
        UniqueConstraint("attempt_id", "raw_fetch_id", name="uq_resolution_attempt_raw_fetch"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("entity_resolution_attempts.id"), nullable=False
    )
    raw_fetch_id: Mapped[int] = mapped_column(ForeignKey("raw_fetches.id"), nullable=False)


class EntityClassification(Base):
    __tablename__ = "entity_classifications"
    __table_args__ = (Index("ix_classification_entity_time", "entity_id", "classified_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("trend_entities.id"), nullable=False)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    category: Mapped[Category] = mapped_column(enum_column(Category), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    classifier_version: Mapped[str] = mapped_column(String(80), nullable=False)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrendSnapshot(Base):
    __tablename__ = "trend_snapshots"
    __table_args__ = (
        UniqueConstraint("entity_id", "as_of", "score_version", name="uq_snapshot_version"),
        Index("ix_snapshot_lifecycle_time", "lifecycle", "as_of"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("trend_entities.id"), nullable=False)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifecycle: Mapped[TrendLifecycle] = mapped_column(enum_column(TrendLifecycle), nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    missing_inputs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    score_version: Mapped[str] = mapped_column(String(80), nullable=False)
    system_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("observation_id", name="uq_evidence_observation"),
        UniqueConstraint(
            "entity_id", "raw_fetch_id", "kind", name="uq_evidence_entity_raw_kind"
        ),
        Index("ix_evidence_entity_time", "entity_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("trend_entities.id"), nullable=False)
    observation_id: Mapped[int | None] = mapped_column(ForeignKey("source_observations.id"))
    resolution_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("entity_resolution_attempts.id")
    )
    raw_fetch_id: Mapped[int | None] = mapped_column(ForeignKey("raw_fetches.id"))
    source: Mapped[Source] = mapped_column(enum_column(Source), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    fact: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "prompt_version",
            "evidence_set_hash",
            "kind",
            name="uq_claim_cache_kind",
        ),
        Index("ix_claim_entity_publishable", "entity_id", "publishable"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("trend_entities.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EvidenceStatus] = mapped_column(enum_column(EvidenceStatus), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    publishable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), nullable=False)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), nullable=False)


class ClaimSnapshot(Base):
    __tablename__ = "claim_snapshots"
    __table_args__ = (
        UniqueConstraint("claim_id", "snapshot_id", name="uq_claim_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), nullable=False)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("trend_snapshots.id"), nullable=False)


class SummaryCache(Base):
    __tablename__ = "summary_cache"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "prompt_version",
            "evidence_set_hash",
            name="uq_summary_cache_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("trend_entities.id"), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    claims_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (Index("ix_review_entity_time", "entity_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("trend_entities.id"), nullable=False)
    product_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_trend_cards.id")
    )
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("trend_snapshots.id"))
    category_at_review: Mapped[Category | None] = mapped_column(enum_column(Category))
    action: Mapped[ReviewAction] = mapped_column(enum_column(ReviewAction), nullable=False)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    previous_status: Mapped[ReviewStatus | None] = mapped_column(enum_column(ReviewStatus))
    resulting_status: Mapped[ReviewStatus | None] = mapped_column(enum_column(ReviewStatus))
    auto_pipeline_result: Mapped[bool | None] = mapped_column(Boolean)
    human_override_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HumanEvaluation(Base):
    __tablename__ = "human_evaluations"
    __table_args__ = (Index("ix_human_eval_entity_time", "entity_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("trend_entities.id"), nullable=False)
    label: Mapped[HumanEvaluationLabel] = mapped_column(
        enum_column(HumanEvaluationLabel), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CostRecord(Base):
    __tablename__ = "cost_records"
    __table_args__ = (Index("ix_cost_time_type", "recorded_at", "cost_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    cost_type: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=Decimal("0"))
    human_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CategorySetting(Base):
    __tablename__ = "category_settings"

    category: Mapped[Category] = mapped_column(enum_column(Category), primary_key=True)
    status: Mapped[CategoryAvailability] = mapped_column(
        enum_column(CategoryAvailability), nullable=False
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProductTrendCard(Base):
    __tablename__ = "product_trend_cards"
    __table_args__ = (
        UniqueConstraint("snapshot_id", name="uq_product_card_snapshot"),
        UniqueConstraint("data_mode", "fixture_key", name="uq_product_card_fixture"),
        CheckConstraint(
            "(data_mode = 'LIVE' AND entity_id IS NOT NULL AND snapshot_id IS NOT NULL "
            "AND pipeline_run_id IS NOT NULL AND fixture_key IS NULL) OR "
            "(data_mode <> 'LIVE' AND fixture_key IS NOT NULL)",
            name="ck_product_card_mode_provenance",
        ),
        Index("ix_product_card_mode_category_time", "data_mode", "category", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    data_mode: Mapped[DataMode] = mapped_column(enum_column(DataMode), nullable=False)
    fixture_key: Mapped[str | None] = mapped_column(String(160))
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("trend_entities.id"))
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("trend_snapshots.id"))
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[Category] = mapped_column(enum_column(Category), nullable=False)
    lifecycle: Mapped[TrendLifecycle] = mapped_column(
        enum_column(TrendLifecycle), nullable=False
    )
    what_text: Mapped[str] = mapped_column(Text, nullable=False)
    interest_text: Mapped[str] = mapped_column(Text, nullable=False)
    cause_text: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trend_score: Mapped[float] = mapped_column(Float, nullable=False)
    auto_pipeline_result: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fixture_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AnonymousUser(Base):
    __tablename__ = "anonymous_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    credential_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    data_mode: Mapped[DataMode] = mapped_column(
        enum_column(DataMode), nullable=False, default=DataMode.LIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserInterest(Base):
    __tablename__ = "user_interests"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_interest"),
        CheckConstraint("category <> 'OTHER'", name="ck_user_interest_not_other"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("anonymous_users.id"), nullable=False)
    category: Mapped[Category] = mapped_column(enum_column(Category), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("anonymous_users.id"), primary_key=True
    )
    mode: Mapped[NotificationMode] = mapped_column(
        enum_column(NotificationMode), nullable=False, default=NotificationMode.OFF
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrendInteraction(Base):
    __tablename__ = "trend_interactions"
    __table_args__ = (UniqueConstraint("user_id", "card_id", name="uq_trend_interaction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("anonymous_users.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(ForeignKey("product_trend_cards.id"), nullable=False)
    first_impression_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_impression_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    impression_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TrendFeedback(Base):
    __tablename__ = "trend_feedback"
    __table_args__ = (UniqueConstraint("user_id", "card_id", name="uq_trend_feedback"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("anonymous_users.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(ForeignKey("product_trend_cards.id"), nullable=False)
    feedback_type: Mapped[FeedbackType] = mapped_column(
        enum_column(FeedbackType), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SavedTrend(Base):
    __tablename__ = "saved_trends"
    __table_args__ = (UniqueConstraint("user_id", "card_id", name="uq_saved_trend"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("anonymous_users.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(ForeignKey("product_trend_cards.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProductEvent(Base):
    __tablename__ = "product_events"
    __table_args__ = (Index("ix_product_event_mode_time", "data_mode", "occurred_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("anonymous_users.id"), nullable=False)
    event_type: Mapped[ProductEventType] = mapped_column(
        enum_column(ProductEventType), nullable=False
    )
    card_id: Mapped[int | None] = mapped_column(ForeignKey("product_trend_cards.id"))
    category: Mapped[Category | None] = mapped_column(enum_column(Category))
    data_mode: Mapped[DataMode] = mapped_column(enum_column(DataMode), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceHealth(Base):
    __tablename__ = "source_health"

    source: Mapped[Source] = mapped_column(enum_column(Source), primary_key=True)
    collector_key: Mapped[str] = mapped_column(String(240), primary_key=True, default="default")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(120))
    freshness_state: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    covered_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RawItem(Base):
    __tablename__ = "raw_items"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            "normalizer_version",
            name="uq_raw_item_source_external_version",
        ),
        Index("ix_raw_item_source_published", "source", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_fetch_id: Mapped[int] = mapped_column(ForeignKey("raw_fetches.id"), nullable=False)
    source: Mapped[Source] = mapped_column(enum_column(Source), nullable=False)
    external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    original_url: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(240))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(500), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    normalizer_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventCluster(Base):
    __tablename__ = "event_clusters"
    __table_args__ = (Index("ix_event_cluster_status_seen", "status", "last_seen_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    canonical_title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ClusterStatus] = mapped_column(enum_column(ClusterStatus), nullable=False)
    clustering_version: Mapped[str] = mapped_column(String(80), nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus), nullable=False, default=ReviewStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EventClusterItem(Base):
    __tablename__ = "event_cluster_items"
    __table_args__ = (
        UniqueConstraint("raw_item_id", name="uq_event_cluster_raw_item"),
        UniqueConstraint("event_cluster_id", "raw_item_id", name="uq_event_cluster_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_cluster_id: Mapped[int] = mapped_column(
        ForeignKey("event_clusters.id"), nullable=False
    )
    raw_item_id: Mapped[int] = mapped_column(ForeignKey("raw_items.id"), nullable=False)
    assignment_method: Mapped[str] = mapped_column(String(80), nullable=False)
    assignment_score: Mapped[float | None] = mapped_column(Float)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    human_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntelligenceEntity(Base):
    __tablename__ = "intelligence_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventEntityLink(Base):
    __tablename__ = "event_entity_links"
    __table_args__ = (
        UniqueConstraint("event_cluster_id", "entity_id", "role", name="uq_event_entity_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_cluster_id: Mapped[int] = mapped_column(
        ForeignKey("event_clusters.id"), nullable=False
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("intelligence_entities.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)


class EventEvidence(Base):
    __tablename__ = "event_evidence"
    __table_args__ = (
        UniqueConstraint("event_cluster_id", "raw_item_id", name="uq_event_evidence_item"),
        Index("ix_event_evidence_event_kind", "event_cluster_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_cluster_id: Mapped[int] = mapped_column(
        ForeignKey("event_clusters.id"), nullable=False
    )
    raw_item_id: Mapped[int] = mapped_column(ForeignKey("raw_items.id"), nullable=False)
    kind: Mapped[EvidenceKind] = mapped_column(enum_column(EvidenceKind), nullable=False)
    fact: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publishable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class EventFact(Base):
    __tablename__ = "event_facts"
    __table_args__ = (
        Index("ix_event_fact_event_publishable", "event_cluster_id", "publishable"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_cluster_id: Mapped[int] = mapped_column(
        ForeignKey("event_clusters.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    publishable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventFactEvidence(Base):
    __tablename__ = "event_fact_evidence"
    __table_args__ = (
        UniqueConstraint("event_fact_id", "event_evidence_id", name="uq_event_fact_evidence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_fact_id: Mapped[int] = mapped_column(ForeignKey("event_facts.id"), nullable=False)
    event_evidence_id: Mapped[int] = mapped_column(
        ForeignKey("event_evidence.id"), nullable=False
    )
    support_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_field: Mapped[str] = mapped_column(String(120), nullable=False)
    validation_result: Mapped[str] = mapped_column(String(40), nullable=False)
    validator_version: Mapped[str] = mapped_column(String(80), nullable=False)


class EventAssessment(Base):
    __tablename__ = "event_assessments"
    __table_args__ = (
        UniqueConstraint(
            "event_cluster_id", "assessment_version", name="uq_event_assessment_version"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_cluster_id: Mapped[int] = mapped_column(
        ForeignKey("event_clusters.id"), nullable=False
    )
    confidence: Mapped[EvidenceConfidence] = mapped_column(
        enum_column(EvidenceConfidence), nullable=False
    )
    confidence_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False)
    importance_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    assessment_version: Mapped[str] = mapped_column(String(80), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DailyBrief(Base):
    __tablename__ = "daily_briefs"
    __table_args__ = (
        UniqueConstraint("brief_date", "version", name="uq_daily_brief_date_version"),
        Index("ix_daily_brief_date_status", "brief_date", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brief_date: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[BriefStatus] = mapped_column(enum_column(BriefStatus), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    today_in_one_line: Mapped[str | None] = mapped_column(Text)
    raw_item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_cluster_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reading_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_version: Mapped[str] = mapped_column(String(80), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False)


class BriefItem(Base):
    __tablename__ = "brief_items"
    __table_args__ = (
        UniqueConstraint("brief_id", "position", name="uq_brief_item_position"),
        UniqueConstraint("brief_id", "event_cluster_id", name="uq_brief_item_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("daily_briefs.id"), nullable=False)
    event_cluster_id: Mapped[int] = mapped_column(
        ForeignKey("event_clusters.id"), nullable=False
    )
    assessment_version: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    what_happened: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    interpretation_text: Mapped[str] = mapped_column(Text, nullable=False)
    watch_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_links: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False)


class BriefItemFact(Base):
    __tablename__ = "brief_item_facts"
    __table_args__ = (
        UniqueConstraint(
            "brief_item_id",
            "event_fact_id",
            "event_evidence_id",
            name="uq_brief_item_fact_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brief_item_id: Mapped[int] = mapped_column(ForeignKey("brief_items.id"), nullable=False)
    event_fact_id: Mapped[int] = mapped_column(ForeignKey("event_facts.id"), nullable=False)
    event_evidence_id: Mapped[int] = mapped_column(
        ForeignKey("event_evidence.id"), nullable=False
    )
    fact_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False)


class BriefReviewSession(Base):
    __tablename__ = "brief_review_sessions"
    __table_args__ = (
        UniqueConstraint(
            "brief_id", "reviewer", name="uq_brief_review_session_brief_reviewer"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brief_id: Mapped[int] = mapped_column(
        ForeignKey("daily_briefs.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[BriefReviewSessionStatus] = mapped_column(
        enum_column(BriefReviewSessionStatus), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_events_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    overall_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BriefReviewReopen(Base):
    __tablename__ = "brief_review_reopens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("brief_review_sessions.id", ondelete="CASCADE"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reopened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    previous_completion_revision: Mapped[int] = mapped_column(Integer, nullable=False)


class BriefReviewActivityPulse(Base):
    __tablename__ = "brief_review_activity_pulses"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "client_event_id", name="uq_brief_review_activity_event"
        ),
        CheckConstraint(
            "active_seconds >= 1 AND active_seconds <= 30",
            name="ck_brief_review_activity_seconds",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("brief_review_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    active_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BriefItemReview(Base):
    __tablename__ = "brief_item_reviews"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "brief_item_id", name="uq_brief_item_review_session_item"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("brief_review_sessions.id", ondelete="CASCADE"), nullable=False
    )
    brief_item_id: Mapped[int] = mapped_column(
        ForeignKey("brief_items.id", ondelete="RESTRICT"), nullable=False
    )
    usefulness: Mapped[BriefItemUsefulness] = mapped_column(
        enum_column(BriefItemUsefulness), nullable=False
    )
    event_selection: Mapped[EventSelectionVerdict] = mapped_column(
        enum_column(EventSelectionVerdict), nullable=False
    )
    fact_correctness: Mapped[FactCorrectness] = mapped_column(
        enum_column(FactCorrectness), nullable=False
    )
    interpretation_quality: Mapped[InterpretationQuality] = mapped_column(
        enum_column(InterpretationQuality), nullable=False
    )
    watch_usefulness: Mapped[WatchUsefulness] = mapped_column(
        enum_column(WatchUsefulness), nullable=False
    )
    verbosity: Mapped[VerbosityVerdict] = mapped_column(
        enum_column(VerbosityVerdict), nullable=False
    )
    evidence_set_usefulness: Mapped[EvidenceSetUsefulness] = mapped_column(
        enum_column(EvidenceSetUsefulness), nullable=False
    )
    incorrect_merge_verdict: Mapped[IncorrectMergeVerdict] = mapped_column(
        enum_column(IncorrectMergeVerdict), nullable=False
    )
    duplicate_escape_verdict: Mapped[DuplicateEscapeVerdict] = mapped_column(
        enum_column(DuplicateEscapeVerdict), nullable=False
    )
    duplicate_of_brief_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("brief_items.id", ondelete="RESTRICT")
    )
    duplicate_of_event_cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("event_clusters.id", ondelete="RESTRICT")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BriefItemReviewMergeMembership(Base):
    __tablename__ = "brief_item_review_merge_memberships"
    __table_args__ = (
        UniqueConstraint(
            "brief_item_review_id",
            "event_cluster_item_id",
            name="uq_brief_item_review_merge_membership",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brief_item_review_id: Mapped[int] = mapped_column(
        ForeignKey("brief_item_reviews.id", ondelete="CASCADE"), nullable=False
    )
    event_cluster_item_id: Mapped[int] = mapped_column(
        ForeignKey("event_cluster_items.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)


class MissingEventReview(Base):
    __tablename__ = "missing_event_reviews"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "canonical_url", name="uq_missing_event_review_session_url"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("brief_review_sessions.id", ondelete="CASCADE"), nullable=False
    )
    canonical_title: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_from: Mapped[MissingEventDiscoverySource] = mapped_column(
        enum_column(MissingEventDiscoverySource), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
