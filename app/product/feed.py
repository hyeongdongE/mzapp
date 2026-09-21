from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai.contracts import UNKNOWN_CAUSE_MESSAGE
from app.models.enums import DataMode, FeedbackType, PublicationPolicyMode
from app.models.tables import (
    CategorySetting,
    Claim,
    ClaimSnapshot,
    PipelineRun,
    ProductTrendCard,
    SavedTrend,
    TrendEntity,
    TrendFeedback,
    TrendInteraction,
    UserInterest,
)
from app.product.policy import PublicationContext, PublicationPolicyEvaluator
from app.product.ranking import personal_rank


class FeedService:
    def __init__(
        self,
        session: Session,
        policy_mode: PublicationPolicyMode,
        *,
        data_mode: DataMode = DataMode.LIVE,
    ) -> None:
        self._session = session
        self._policy = PublicationPolicyEvaluator(policy_mode)
        self._data_mode = data_mode

    def eligible_cards(self, user_id: str) -> list[ProductTrendCard]:
        if self._data_mode is not DataMode.LIVE:
            return []
        interests = set(
            self._session.scalars(
                select(UserInterest.category).where(UserInterest.user_id == user_id)
            )
        )
        if not interests:
            return []
        rows = self._session.execute(
            select(ProductTrendCard, TrendEntity, PipelineRun, CategorySetting)
            .join(TrendEntity, TrendEntity.id == ProductTrendCard.entity_id)
            .join(PipelineRun, PipelineRun.id == ProductTrendCard.pipeline_run_id)
            .join(CategorySetting, CategorySetting.category == ProductTrendCard.category)
            .where(
                ProductTrendCard.data_mode == DataMode.LIVE,
                ProductTrendCard.category.in_(interests),
            )
        ).all()
        eligible = []
        for card, entity, run, category in rows:
            publishable_count = self._session.scalar(
                select(func.count())
                .select_from(Claim)
                .join(ClaimSnapshot, ClaimSnapshot.claim_id == Claim.id)
                .where(
                    ClaimSnapshot.snapshot_id == card.snapshot_id,
                    Claim.publishable.is_(True),
                )
            )
            decision = self._policy.evaluate(
                PublicationContext(
                    data_mode=card.data_mode,
                    run_kind=run.kind,
                    run_status=run.status,
                    has_publishable_claims=bool(publishable_count),
                    category_status=category.status,
                    review_status=entity.review_status,
                    suppressed=card.suppressed,
                    auto_pipeline_result=card.auto_pipeline_result,
                )
            )
            if decision.publish:
                eligible.append(card)
        return eligible

    def ranked_items(self, user_id: str, now: datetime | None = None) -> list[dict]:
        timestamp = now or datetime.now(UTC)
        cards = self.eligible_cards(user_id)
        feedback = {
            row.card_id: row
            for row in self._session.scalars(
                select(TrendFeedback).where(TrendFeedback.user_id == user_id)
            )
        }
        interactions = {
            row.card_id: row
            for row in self._session.scalars(
                select(TrendInteraction).where(TrendInteraction.user_id == user_id)
            )
        }
        saved_ids = set(
            self._session.scalars(
                select(SavedTrend.card_id).where(SavedTrend.user_id == user_id)
            )
        )
        ranked = [
            (
                *personal_rank(
                    card,
                    feedback=feedback.get(card.id),
                    interaction=interactions.get(card.id),
                    saved=card.id in saved_ids,
                    now=timestamp,
                ),
                card,
            )
            for card in cards
        ]
        ranked.sort(key=lambda row: (-row[0], -row[2].observed_at.timestamp(), row[2].public_id))
        return [
            self.serialize_card(
                card,
                saved=card.id in saved_ids,
                feedback=feedback.get(card.id),
                reasons=reasons,
            )
            for _, reasons, card in ranked
        ]

    def get_eligible(self, user_id: str, public_id: str) -> ProductTrendCard | None:
        return next(
            (card for card in self.eligible_cards(user_id) if card.public_id == public_id),
            None,
        )

    def detail(self, user_id: str, card: ProductTrendCard) -> dict:
        feedback = self._session.scalar(
            select(TrendFeedback).where(
                TrendFeedback.user_id == user_id, TrendFeedback.card_id == card.id
            )
        )
        saved = self._session.scalar(
            select(SavedTrend.id).where(
                SavedTrend.user_id == user_id, SavedTrend.card_id == card.id
            )
        )
        result = self.serialize_card(card, saved=saved is not None, feedback=feedback)
        result.update(
            {
                "what": card.what_text,
                "why": card.cause_text or UNKNOWN_CAUSE_MESSAGE,
                "sources": card.sources,
            }
        )
        return result

    def record_open(self, user_id: str, card_id: int) -> None:
        interaction = self._interaction(user_id, card_id)
        interaction.open_count += 1
        self._session.flush()

    def feedback(
        self, user_id: str, card_id: int, feedback_type: FeedbackType, now: datetime | None = None
    ) -> TrendFeedback:
        timestamp = now or datetime.now(UTC)
        row = self._session.scalar(
            select(TrendFeedback).where(
                TrendFeedback.user_id == user_id, TrendFeedback.card_id == card_id
            )
        )
        if row is None:
            row = TrendFeedback(
                user_id=user_id,
                card_id=card_id,
                feedback_type=feedback_type,
                created_at=timestamp,
                updated_at=timestamp,
            )
            self._session.add(row)
        else:
            row.feedback_type = feedback_type
            row.updated_at = timestamp
        self._session.flush()
        return row

    def save(self, user_id: str, card_id: int, now: datetime | None = None) -> None:
        existing = self._session.scalar(
            select(SavedTrend).where(
                SavedTrend.user_id == user_id, SavedTrend.card_id == card_id
            )
        )
        if existing is None:
            self._session.add(
                SavedTrend(
                    user_id=user_id,
                    card_id=card_id,
                    created_at=now or datetime.now(UTC),
                )
            )
            self._session.flush()

    def unsave(self, user_id: str, card_id: int) -> None:
        self._session.execute(
            delete(SavedTrend).where(
                SavedTrend.user_id == user_id, SavedTrend.card_id == card_id
            )
        )
        self._session.flush()

    def saved_items(self, user_id: str) -> list[dict]:
        eligible = {card.id: card for card in self.eligible_cards(user_id)}
        rows = list(
            self._session.scalars(
                select(SavedTrend)
                .where(SavedTrend.user_id == user_id)
                .order_by(SavedTrend.created_at.desc())
            )
        )
        return [
            self.serialize_card(eligible[row.card_id], saved=True, feedback=None)
            for row in rows
            if row.card_id in eligible
        ]

    def _interaction(self, user_id: str, card_id: int) -> TrendInteraction:
        row = self._session.scalar(
            select(TrendInteraction).where(
                TrendInteraction.user_id == user_id, TrendInteraction.card_id == card_id
            )
        )
        if row is None:
            row = TrendInteraction(
                user_id=user_id, card_id=card_id, impression_count=0, open_count=0
            )
            self._session.add(row)
        return row

    @staticmethod
    def serialize_card(
        card: ProductTrendCard,
        *,
        saved: bool,
        feedback: TrendFeedback | None,
        reasons: list[str] | None = None,
    ) -> dict:
        return {
            "trendId": card.public_id,
            "title": card.title,
            "category": card.category.value,
            "lifecycle": card.lifecycle.value,
            "summary": card.interest_text,
            "firstSeenAt": card.first_seen_at.isoformat(),
            "observedAt": card.observed_at.isoformat(),
            "sourceNames": sorted({source["source"] for source in card.sources}),
            "saved": saved,
            "feedback": feedback.feedback_type.value if feedback else None,
            "rankingReasons": reasons or [],
        }
