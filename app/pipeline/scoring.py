from __future__ import annotations

from dataclasses import dataclass

WEIGHTS = {
    "velocity": 0.30,
    "novelty": 0.25,
    "persistence": 0.20,
    "cross_source": 0.25,
    "baseline_penalty": -0.10,
    "repetition_penalty": -0.05,
    "news_only_penalty": -0.05,
}


@dataclass(frozen=True)
class TrendSignal:
    velocity: float
    novelty: float
    persistence: float
    cross_source: float
    baseline_penalty: float
    repetition_penalty: float
    news_only_penalty: float


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    components: dict[str, float]
    weights: dict[str, float]
    contributions: dict[str, float]
    missing_inputs: tuple[str, ...]
    interpretation: str = "internal_relative_score_not_probability"


class ExplainableScorer:
    def score(
        self, signal: TrendSignal, *, missing_inputs: tuple[str, ...] = ()
    ) -> ScoreBreakdown:
        components = {
            name: float(getattr(signal, name))
            for name in WEIGHTS
        }
        if any(value < 0 or value > 1 for value in components.values()):
            raise ValueError("score components must be between 0 and 1")
        contributions = {
            name: round(100 * WEIGHTS[name] * value, 4)
            for name, value in components.items()
        }
        total = round(min(100.0, max(0.0, sum(contributions.values()))), 2)
        return ScoreBreakdown(
            total=total,
            components=components,
            weights=dict(WEIGHTS),
            contributions=contributions,
            missing_inputs=tuple(sorted(set(missing_inputs))),
        )
