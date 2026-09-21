from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    Category,
    DataMode,
    FeedbackType,
    HumanEvaluationLabel,
    ProductEventType,
    PublicationPolicyMode,
    ReviewStatus,
)
from app.models.tables import (
    AnonymousUser,
    CategorySetting,
    Claim,
    ClaimSnapshot,
    HumanEvaluation,
    PipelineRun,
    ProductEvent,
    ProductTrendCard,
    Review,
    SavedTrend,
    TrendEntity,
    TrendFeedback,
    TrendInteraction,
    TrendSnapshot,
)
from app.product.policy import PublicationContext, PublicationPolicyEvaluator


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ProductAnalytics:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        user: AnonymousUser,
        event_type: ProductEventType,
        *,
        card: ProductTrendCard | None = None,
        category: Category | None = None,
        now: datetime | None = None,
    ) -> ProductEvent:
        mode = card.data_mode if card is not None else user.data_mode
        event = ProductEvent(
            user_id=user.id,
            event_type=event_type,
            card_id=card.id if card else None,
            category=category or (card.category if card else None),
            data_mode=mode,
            occurred_at=now or datetime.now(UTC),
        )
        self._session.add(event)
        self._session.flush()
        return event

    def impression(
        self, user: AnonymousUser, card: ProductTrendCard, now: datetime | None = None
    ) -> None:
        timestamp = now or datetime.now(UTC)
        interaction = self._session.scalar(
            select(TrendInteraction).where(
                TrendInteraction.user_id == user.id,
                TrendInteraction.card_id == card.id,
            )
        )
        if interaction is None:
            interaction = TrendInteraction(
                user_id=user.id,
                card_id=card.id,
                first_impression_at=timestamp,
                last_impression_at=timestamp,
                impression_count=1,
                open_count=0,
            )
            self._session.add(interaction)
        else:
            if (
                interaction.last_impression_at is not None
                and timestamp - _utc(interaction.last_impression_at) < timedelta(minutes=5)
            ):
                return
            interaction.first_impression_at = interaction.first_impression_at or timestamp
            interaction.last_impression_at = timestamp
            interaction.impression_count += 1
        self.record(user, ProductEventType.TREND_IMPRESSION, card=card, now=timestamp)

    def summary(self, mode: DataMode = DataMode.LIVE) -> dict[str, float | int | None]:
        interactions = list(
            self._session.scalars(
                select(TrendInteraction)
                .join(ProductTrendCard, ProductTrendCard.id == TrendInteraction.card_id)
                .where(ProductTrendCard.data_mode == mode)
            )
        )
        impressions = sum(row.impression_count for row in interactions)
        opens = sum(row.open_count for row in interactions)
        feedback = list(
            self._session.scalars(
                select(TrendFeedback)
                .join(ProductTrendCard, ProductTrendCard.id == TrendFeedback.card_id)
                .where(ProductTrendCard.data_mode == mode)
            )
        )
        counts = Counter(row.feedback_type for row in feedback)
        feedback_total = len(feedback)
        saves = self._session.scalar(
            select(func.count())
            .select_from(SavedTrend)
            .join(ProductTrendCard, ProductTrendCard.id == SavedTrend.card_id)
            .where(ProductTrendCard.data_mode == mode)
        ) or 0
        users = list(
            self._session.scalars(
                select(AnonymousUser).where(AnonymousUser.data_mode == mode)
            )
        )
        d1 = sum(
            (user.last_seen_at - user.created_at).total_seconds() >= 86400 for user in users
        )
        d7 = sum(
            (user.last_seen_at - user.created_at).total_seconds() >= 604800 for user in users
        )
        return {
            "users": len(users),
            "impressions": impressions,
            "opens": opens,
            "feedback_total": feedback_total,
            "new_and_useful": counts[FeedbackType.NEW_AND_USEFUL],
            "already_knew": counts[FeedbackType.ALREADY_KNEW],
            "not_interested": counts[FeedbackType.NOT_INTERESTED],
            "incorrect": counts[FeedbackType.INCORRECT],
            "saves": saves,
            "discovery_value_rate": _rate(
                counts[FeedbackType.NEW_AND_USEFUL], feedback_total
            ),
            "already_known_rate": _rate(counts[FeedbackType.ALREADY_KNEW], feedback_total),
            "interest_failure_rate": _rate(
                counts[FeedbackType.NOT_INTERESTED], feedback_total
            ),
            "incorrect_rate": _rate(counts[FeedbackType.INCORRECT], feedback_total),
            "open_rate": _rate(opens, impressions),
            "save_rate": _rate(saves, impressions),
            "d1_return_rate": _rate(d1, len(users)),
            "d7_return_rate": _rate(d7, len(users)),
        }

    def category_performance(
        self, *, now: datetime | None = None, window_days: int = 14
    ) -> list[dict[str, object]]:
        if window_days <= 0:
            raise ValueError("window_days must be positive")
        window_end = now or datetime.now(UTC)
        window_start = window_end - timedelta(days=window_days)
        latest_review_ids = (
            select(func.max(Review.id))
            .where(
                Review.product_card_id.is_not(None),
                Review.created_at >= window_start,
                Review.created_at <= window_end,
            )
            .group_by(Review.product_card_id)
        )
        rows: list[dict[str, object]] = []
        for category in Category:
            if category is Category.OTHER:
                continue
            evaluations = list(
                self._session.scalars(
                    select(HumanEvaluation)
                    .join(TrendEntity, TrendEntity.id == HumanEvaluation.entity_id)
                    .where(
                        TrendEntity.category == category,
                        HumanEvaluation.created_at >= window_start,
                        HumanEvaluation.created_at <= window_end,
                    )
                )
            )
            labels = Counter(row.label for row in evaluations)
            reviewed = len(evaluations)
            usable = labels[HumanEvaluationLabel.VALID_TREND]
            noise = sum(
                labels[label]
                for label in (
                    HumanEvaluationLabel.TOO_OBVIOUS,
                    HumanEvaluationLabel.NEWS_ONLY,
                    HumanEvaluationLabel.NOT_USEFUL,
                )
            )
            feedback = list(
                self._session.scalars(
                    select(TrendFeedback)
                    .join(ProductTrendCard, ProductTrendCard.id == TrendFeedback.card_id)
                    .where(
                        ProductTrendCard.data_mode == DataMode.LIVE,
                        ProductTrendCard.category == category,
                        ProductTrendCard.observed_at >= window_start,
                        ProductTrendCard.observed_at <= window_end,
                    )
                )
            )
            feedback_counts = Counter(row.feedback_type for row in feedback)
            cards = list(
                self._session.scalars(
                    select(ProductTrendCard)
                    .where(
                        ProductTrendCard.data_mode == DataMode.LIVE,
                        ProductTrendCard.category == category,
                        ProductTrendCard.observed_at >= window_start,
                        ProductTrendCard.observed_at <= window_end,
                    )
                )
            )
            latest_reviews = list(
                self._session.scalars(
                    select(Review).where(
                        Review.id.in_(latest_review_ids),
                        Review.category_at_review == category,
                    )
                )
            )
            auto_reviews = [
                review
                for review in latest_reviews
                if review.auto_pipeline_result is True
            ]
            approved = sum(
                review.resulting_status is ReviewStatus.APPROVED for review in auto_reviews
            )
            rejected = sum(
                review.resulting_status in (ReviewStatus.REJECTED, ReviewStatus.NOISE)
                for review in auto_reviews
            )
            claims = list(
                self._session.scalars(
                    select(Claim)
                    .join(ClaimSnapshot, ClaimSnapshot.claim_id == Claim.id)
                    .join(
                        ProductTrendCard,
                        ProductTrendCard.snapshot_id == ClaimSnapshot.snapshot_id,
                    )
                    .where(
                        ProductTrendCard.data_mode == DataMode.LIVE,
                        ProductTrendCard.category == category,
                        ProductTrendCard.observed_at >= window_start,
                        ProductTrendCard.observed_at <= window_end,
                    )
                    .distinct()
                )
            )
            unsupported = sum(not claim.publishable for claim in claims)
            shadow_eligible = sum(self._shadow_auto_eligible(card) for card in cards)
            rows.append(
                {
                    "category": category.value,
                    "window_days": window_days,
                    "valid_trends_per_day": round(usable / window_days, 2),
                    "usable_card_rate": _rate(usable, reviewed),
                    "noise_rate": _rate(noise, reviewed),
                    "false_positive_rate": _rate(reviewed - usable, reviewed),
                    "unsupported_claim_rate": _rate(unsupported, len(claims)),
                    "discovery_value_rate": _rate(
                        feedback_counts[FeedbackType.NEW_AND_USEFUL], len(feedback)
                    ),
                    "already_known_rate": _rate(
                        feedback_counts[FeedbackType.ALREADY_KNEW], len(feedback)
                    ),
                    "incorrect_feedback_rate": _rate(
                        feedback_counts[FeedbackType.INCORRECT], len(feedback)
                    ),
                    "auto_publishable_cards": sum(
                        card.auto_pipeline_result for card in cards
                    ),
                    "shadow_auto_eligible_cards": shadow_eligible,
                    "human_reviewed_cards": len(latest_reviews),
                    "auto_publishable_reviewed": len(auto_reviews),
                    "human_approval_rate": _rate(approved, len(auto_reviews)),
                    "review_rejection_rate": _rate(rejected, len(auto_reviews)),
                }
            )
        return rows

    def _shadow_auto_eligible(self, card: ProductTrendCard) -> bool:
        row = self._session.execute(
            select(TrendEntity, TrendSnapshot, PipelineRun, CategorySetting)
            .select_from(TrendEntity)
            .join(TrendSnapshot, TrendSnapshot.id == card.snapshot_id)
            .join(PipelineRun, PipelineRun.id == card.pipeline_run_id)
            .join(CategorySetting, CategorySetting.category == TrendEntity.category)
            .where(
                TrendEntity.id == card.entity_id,
                TrendEntity.category == card.category,
                TrendSnapshot.entity_id == card.entity_id,
                TrendSnapshot.pipeline_run_id == card.pipeline_run_id,
            )
        ).one_or_none()
        if row is None:
            return False
        entity, _snapshot, run, category = row
        claim_kinds = set(
            self._session.scalars(
                select(Claim.kind)
                .join(ClaimSnapshot, ClaimSnapshot.claim_id == Claim.id)
                .where(
                    ClaimSnapshot.snapshot_id == card.snapshot_id,
                    Claim.entity_id == card.entity_id,
                    Claim.publishable.is_(True),
                )
            )
        )
        decision = PublicationPolicyEvaluator(
            PublicationPolicyMode.AUTO_PUBLISH_ELIGIBLE
        ).evaluate(
            PublicationContext(
                data_mode=card.data_mode,
                run_kind=run.kind,
                run_status=run.status,
                has_publishable_claims={"WHAT", "INTEREST"} <= claim_kinds,
                category_status=category.status,
                review_status=entity.review_status,
                suppressed=card.suppressed,
                auto_pipeline_result=card.auto_pipeline_result,
            )
        )
        return decision.auto_publish_eligible
