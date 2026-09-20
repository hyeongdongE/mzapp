from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.enums import TrendLifecycle


@dataclass(frozen=True)
class LifecycleContext:
    first_seen_at: datetime
    current_strength: float
    previous_strength: float
    current_observations: int
    score: float
    baseline_presence: float
    previous_lifecycle: TrendLifecycle | None = None
    high_score_windows: int = 0
    high_score_duration_hours: float = 0.0


class LifecycleDetector:
    def detect(
        self, context: LifecycleContext, as_of: datetime
    ) -> TrendLifecycle | None:
        if (
            context.previous_lifecycle in {TrendLifecycle.RISING, TrendLifecycle.HOT}
            and context.previous_strength > 0
            and context.current_strength <= context.previous_strength * 0.60
        ):
            return TrendLifecycle.COOLING
        if (
            context.score >= 70
            and context.current_observations >= 1
            and (
                context.high_score_windows >= 3
                or context.high_score_duration_hours >= 6
            )
        ):
            return TrendLifecycle.HOT
        if (
            context.current_observations >= 2
            and context.current_strength > 0
            and (
                context.previous_strength == 0
                or context.current_strength >= context.previous_strength * 1.25
            )
        ):
            return TrendLifecycle.RISING
        age_hours = (as_of - context.first_seen_at).total_seconds() / 3600
        if age_hours <= 24 and context.baseline_presence == 0:
            return TrendLifecycle.NEW
        if context.previous_lifecycle is not TrendLifecycle.NEW:
            return context.previous_lifecycle
        return None
