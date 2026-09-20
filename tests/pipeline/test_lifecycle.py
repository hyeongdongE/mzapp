from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import TrendLifecycle
from app.pipeline.lifecycle import LifecycleContext, LifecycleDetector

AS_OF = datetime(2026, 9, 21, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        (
            LifecycleContext(
                first_seen_at=AS_OF - timedelta(hours=1),
                current_strength=1,
                previous_strength=0,
                current_observations=1,
                score=55,
                baseline_presence=0,
            ),
            TrendLifecycle.NEW,
        ),
        (
            LifecycleContext(
                first_seen_at=AS_OF - timedelta(days=2),
                current_strength=1,
                previous_strength=0.5,
                current_observations=2,
                score=60,
                baseline_presence=0.1,
            ),
            TrendLifecycle.RISING,
        ),
        (
            LifecycleContext(
                first_seen_at=AS_OF - timedelta(days=3),
                current_strength=1,
                previous_strength=0.8,
                current_observations=3,
                score=75,
                baseline_presence=0.1,
                high_score_windows=3,
                high_score_duration_hours=7,
            ),
            TrendLifecycle.HOT,
        ),
        (
            LifecycleContext(
                first_seen_at=AS_OF - timedelta(days=4),
                current_strength=0.4,
                previous_strength=1,
                current_observations=1,
                score=35,
                baseline_presence=0.2,
                previous_lifecycle=TrendLifecycle.HOT,
            ),
            TrendLifecycle.COOLING,
        ),
    ],
)
def test_lifecycle_precedence(context: LifecycleContext, expected: TrendLifecycle) -> None:
    assert LifecycleDetector().detect(context, AS_OF) is expected


def test_single_news_spike_cannot_be_hot_even_with_high_score() -> None:
    context = LifecycleContext(
        first_seen_at=AS_OF - timedelta(hours=1),
        current_strength=1,
        previous_strength=0,
        current_observations=1,
        score=90,
        baseline_presence=0,
        high_score_windows=1,
    )

    assert LifecycleDetector().detect(context, AS_OF) is TrendLifecycle.NEW


def test_old_weak_entity_without_prior_state_is_not_mislabeled_new() -> None:
    context = LifecycleContext(
        first_seen_at=AS_OF - timedelta(days=2),
        current_strength=0.1,
        previous_strength=0.1,
        current_observations=1,
        score=10,
        baseline_presence=0.5,
    )

    assert LifecycleDetector().detect(context, AS_OF) is None
