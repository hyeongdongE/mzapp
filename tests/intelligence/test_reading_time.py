from __future__ import annotations

from app.intelligence.reading_time import ReadingTimeEstimator


def test_korean_latin_and_mixed_reading_time() -> None:
    estimator = ReadingTimeEstimator()

    assert estimator.estimate_seconds("가" * 500) == 60
    assert estimator.estimate_seconds("word " * 200) == 60
    assert estimator.estimate_seconds(("가" * 250) + " " + ("word " * 100)) == 60


def test_300_seconds_passes_and_301_seconds_exceeds_gate() -> None:
    estimator = ReadingTimeEstimator()

    assert estimator.estimate_seconds("가" * 2500) == 300
    assert estimator.estimate_seconds("가" * 2501) == 301
