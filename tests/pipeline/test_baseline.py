from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.models.enums import Source
from app.pipeline.baseline import BaselineAnalyzer, SignalPoint

AS_OF = datetime(2026, 9, 21, 0, 0, tzinfo=UTC)


def point(
    days_ago: int,
    *,
    text: str = "위키백과 대문",
    source: Source = Source.WIKIMEDIA,
    metric: float | None = 1000,
    rank: int | None = 1,
) -> SignalPoint:
    timestamp = AS_OF - timedelta(days=days_ago)
    return SignalPoint(
        source=source,
        source_timestamp=timestamp,
        observed_at=timestamp,
        normalized_text=text,
        metric=metric,
        rank=rank,
        news_count=0,
        candidate_id=1,
    )


def test_permanent_structural_baseline_item_receives_full_penalty() -> None:
    history = [point(days_ago) for days_ago in range(1, 29)]

    stats = BaselineAnalyzer().compute(history, AS_OF)

    assert stats.presence_ratio == 1.0
    assert stats.structural_noise is True
    assert stats.penalty == 1.0
    assert stats.median_rank == 1
    assert stats.median_metric == 1000


def test_baseline_excludes_future_source_or_acquisition_rows() -> None:
    future_source = point(1, text="future-source")
    future_source = replace(future_source, source_timestamp=AS_OF + timedelta(hours=1))
    learned_later = point(1, text="learned-later")
    learned_later = replace(learned_later, observed_at=AS_OF + timedelta(hours=1))

    stats = BaselineAnalyzer().compute(
        [point(1, text="valid"), future_source, learned_later], AS_OF
    )

    assert stats.observation_count == 1
    assert stats.presence_ratio == 1 / 28


def test_google_news_only_is_explicit_and_not_a_hard_rejection() -> None:
    value = point(1, text="breaking", source=Source.GOOGLE_TRENDS, rank=None)
    value = replace(value, news_count=3)

    stats = BaselineAnalyzer().compute([value], AS_OF)

    assert stats.news_only is True
    assert stats.source_count == 1
