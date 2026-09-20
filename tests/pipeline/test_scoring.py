import pytest

from app.pipeline.scoring import ExplainableScorer, TrendSignal


def signal(**overrides: float) -> TrendSignal:
    values = {
        "velocity": 1.0,
        "novelty": 1.0,
        "persistence": 0.5,
        "cross_source": 1.0,
        "baseline_penalty": 0.2,
        "repetition_penalty": 0.0,
        "news_only_penalty": 0.0,
    }
    values.update(overrides)
    return TrendSignal(**values)


def test_score_components_are_explainable_and_formula_is_exact() -> None:
    result = ExplainableScorer().score(signal(), missing_inputs=("wikimedia.views_ceil",))

    assert result.total == 88.0
    assert set(result.components) == {
        "velocity",
        "novelty",
        "persistence",
        "cross_source",
        "baseline_penalty",
        "repetition_penalty",
        "news_only_penalty",
    }
    assert result.weights["velocity"] == 0.30
    assert result.contributions["baseline_penalty"] == -2.0
    assert result.missing_inputs == ("wikimedia.views_ceil",)


def test_score_is_clamped_and_rejects_out_of_range_components() -> None:
    assert ExplainableScorer().score(signal(baseline_penalty=1, repetition_penalty=1)).total >= 0
    with pytest.raises(ValueError, match="0 and 1"):
        ExplainableScorer().score(signal(velocity=1.1))


def test_single_news_source_spike_does_not_receive_cross_source_bonus() -> None:
    result = ExplainableScorer().score(
        signal(
            persistence=0.25,
            cross_source=0,
            baseline_penalty=0,
            news_only_penalty=1,
        )
    )

    assert result.total == 55.0
