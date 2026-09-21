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
    ReviewStatus,
)
from app.models.tables import (
    AnonymousUser,
    Claim,
    ClaimSnapshot,
    HumanEvaluation,
    ProductEvent,
    ProductTrendCard,
    Review,
    SavedTrend,
    TrendEntity,
    TrendFeedback,
    TrendInteraction,
)


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

    def category_performance(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for category in Category:
            if category is Category.OTHER:
                continue
            evaluations = list(
                self._session.scalars(
                    select(HumanEvaluation)
                    .join(TrendEntity, TrendEntity.id == HumanEvaluation.entity_id)
                    .where(TrendEntity.category == category)
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
            days = len({row.created_at.date() for row in evaluations})
            feedback = list(
                self._session.scalars(
                    select(TrendFeedback)
                    .join(ProductTrendCard, ProductTrendCard.id == TrendFeedback.card_id)
                    .where(
                        ProductTrendCard.data_mode == DataMode.LIVE,
                        ProductTrendCard.category == category,
                    )
                )
            )
            feedback_counts = Counter(row.feedback_type for row in feedback)
            auto_reviews = list(
                self._session.scalars(
                    select(Review)
                    .join(TrendEntity, TrendEntity.id == Review.entity_id)
                    .where(
                        TrendEntity.category == category,
                        Review.auto_pipeline_result.is_(True),
                    )
                )
            )
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
                    )
                    .distinct()
                )
            )
            unsupported = sum(not claim.publishable for claim in claims)
            rows.append(
                {
                    "category": category.value,
                    "valid_trends_per_day": round(usable / days, 2) if days else None,
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
                    "auto_publishable_reviewed": len(auto_reviews),
                    "human_approval_rate": _rate(approved, len(auto_reviews)),
                    "review_rejection_rate": _rate(rejected, len(auto_reviews)),
                }
            )
        return rows
