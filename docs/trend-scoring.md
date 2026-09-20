# Trend Detection and Scoring

`score-v1` is a deterministic internal ranking score. It is not a probability, confidence, forecast,
or statement that an entity will become popular. Every persisted snapshot includes
`internal_relative_score_not_probability` plus the raw components, weights, signed contributions,
input statistics, missing inputs, cutoff, and detection time.

## Cutoff and windows

An observation is usable only when both `source_timestamp <= as_of` and `observed_at <= as_of`.
Database-backed live scoring accepts cutoffs within five minutes of the actual run only; historical
replay remains disabled until Phase 8 supplies historical entity projections.

Source windows reflect official publication lag:

- Google Trends RSS: current 24 hours and previous 24 hours.
- Wikimedia top pages: current 72 hours and previous 72 hours, covering the documented two-day API
  lag without pretending the daily value is real-time.
- Baseline: the 28 days immediately before each source's current window.

Google strength uses `log1p(approx_traffic_lower_bound)` against a fixed source cap. Wikimedia uses
`log1p(views_ceil)` and falls back to inverse rank only when views are absent. Missing metrics are
listed in `missing_inputs`; they reduce only the affected signal rather than being invented.

## Components

All components are clamped to 0–1.

- `velocity`: positive relative change from the previous source-aligned window; declines receive 0
  here and are handled by lifecycle cooling.
- `novelty`: one minus 28-day presence ratio; structural/static pages receive 0.
- `persistence`: distinct six-hour buckets in the current window, capped at four.
- `cross_source`: 1 only when both official discovery sources independently occur in their current
  windows. A missing second source never rejects the candidate by itself.
- `baseline_penalty`: 28-day presence ratio, forced to 1 for main pages and `Special:`/`특수:` pages.
- `repetition_penalty`: multiple distinct normalized aliases for the same entity in the current
  window. The same normalized name from two sources is not penalized.
- `news_only_penalty`: Google-only current signal with attached news items.

The exact formula is:

```text
100 × (
  0.30 velocity + 0.25 novelty + 0.20 persistence + 0.25 cross_source
  - 0.10 baseline_penalty - 0.05 repetition_penalty - 0.05 news_only_penalty
)
```

The result is clamped to 0–100. A single new Google/news observation receives 55 at most under the
default components and cannot become `HOT`, even if one metric is large. Sports are not globally
penalized merely for being sports; personalization/category selection handles relevance, while the
same persistence, baseline, news-only, and cross-source rules apply to event spikes.

## Lifecycle

Rules use precedence `COOLING`, `HOT`, `RISING`, `NEW`:

- `COOLING`: prior `RISING`/`HOT` and current strength is at most 60% of the previous window.
- `HOT`: score at least 70, with three high-score snapshot windows or six hours of sustained high
  score.
- `RISING`: at least two current observations and strength at least 25% above the previous window
  (or positive after an empty previous window).
- `NEW`: first seen within 24 hours, absent from baseline.

An old weak entity with no prior lifecycle is not mislabeled `NEW`; no snapshot is published. With a
prior state, a low-signal entity retains that state unless the cooling rule applies.

## Verification

- Unit/full regression: 94 passed and 8 opt-in integration tests skipped; Ruff passed.
- Live PoC DB run 10 completed with zero snapshots because its only resolved entity was an old
  structural Wikimedia baseline item. This is intentional suppression, not missing output.
- A fresh PostgreSQL database persisted a two-window Google fixture as `RISING`, score `60.0`, with
  news-only penalty `1.0`, UTC timestamps, and the complete JSON breakdown. The temporary database
  was removed after inspection.
- Targeted official Wikidata runs 7–9 stayed `NEEDS_REVIEW` for ambiguous/unavailable matches and
  therefore produced no score, confirming unresolved entities cannot leak into snapshots.
