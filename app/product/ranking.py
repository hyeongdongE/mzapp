from __future__ import annotations

from datetime import UTC, datetime

from app.models.enums import FeedbackType
from app.models.tables import ProductTrendCard, TrendFeedback, TrendInteraction


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def personal_rank(
    card: ProductTrendCard,
    *,
    feedback: TrendFeedback | None,
    interaction: TrendInteraction | None,
    saved: bool,
    now: datetime,
) -> tuple[float, list[str]]:
    score = card.trend_score / 10.0 + 10.0
    reasons = ["선택한 관심 분야", "최근 관측된 변화"]
    age_hours = max(0.0, (now - _utc(card.observed_at)).total_seconds() / 3600)
    score += max(0.0, 3.0 - age_hours / 24.0)
    if saved:
        score += 3.0
        reasons.append("저장한 관심 기록")
    if interaction is not None:
        score -= min(interaction.impression_count, 5) * 1.5
    if feedback is not None:
        if feedback.feedback_type is FeedbackType.NEW_AND_USEFUL:
            score += 5.0
            reasons.append("유용하다고 표시한 주제")
        elif feedback.feedback_type is FeedbackType.ALREADY_KNEW:
            score -= 50.0
        elif feedback.feedback_type in (FeedbackType.NOT_INTERESTED, FeedbackType.INCORRECT):
            score -= 100.0
    return score, reasons
