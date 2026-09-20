# Evaluation metrics and reports

Evaluation uses explicit UTC half-open periods (`start <= timestamp < end`). It computes facts from
stored official observations and append-only review history; it does not interpret a trend score as
a probability. Every zero denominator is rendered as `N/A`, never as `0%`.

## Daily formulas

| Metric | Definition |
|---|---|
| Raw candidates | Google Trends and Wikimedia source observations acquired during the UTC day |
| Unique candidates | `trend_candidates` whose source-derived `first_seen_at` is during the day |
| Trend entities | Distinct entities with a trend snapshot whose `as_of` is during the day |
| Approved cards | Distinct entities receiving an `APPROVE` review during the day |
| Category candidates | Distinct snapshotted or approved entities assigned to the category as of period end |
| Category valid cards | Those category entities approved during the day |
| Precision | `VALID_TREND / all human evaluation records` |
| Duplicate rate | `DUPLICATE / all human evaluation records` |
| Noise rate | `(TOO_OBVIOUS + NEWS_ONLY + NOT_USEFUL) / all human evaluation records` |
| Classification error rate | `WRONG_CATEGORY / all human evaluation records` |
| Merge error rate | `BAD_ENTITY_MERGE / all human evaluation records` |
| Unsupported summary rate | Non-publishable claims / all claims checked during the day |
| Cross-source rate | Snapshotted entities observed in both Google Trends and Wikimedia / entities observed in either |
| Detection delay | First persisted `system_detected_at` minus first eligible official acquisition time |
| Approval delay | First approval time minus the entity's original detection time |
| Total cost | Stored amount plus `human_minutes / 60 * metadata_json.hourly_rate`, USD only |
| Cost per approved card | Total cost / approved cards |

Category is reconstructed from the last classification or audited `CHANGE_CATEGORY` action before
period end. Source observations and entity links are also cutoff at period end. A day is marked
complete only when both Google Trends and Wikimedia have a successful collection run that day.

Freshness reports nearest-rank P50 and P95. Negative intervals are rejected as data integrity errors.
Mixed/non-USD cost records are rejected instead of being silently combined without exchange rates.

## Weekly aggregation

Weekly reports aggregate seven `DailyEvaluation` facts. Counts and cost are summed, rates are
recomputed from stored daily numerators/denominators, freshness percentiles are recomputed from the
daily delay samples, and versions are unioned. `Complete days` counts only days with both official
discovery-source collections, so empty calendar days cannot satisfy the 14-day evidence threshold.

The PoC decision remains `CONTINUE_DATA_COLLECTION`. The evaluator never emits
`READY_FOR_USER_MVP` from fewer than 14 complete days, and currently does not make that promotion
automatically without an agreed product threshold.

## Commands

```powershell
$env:DATABASE_URL='postgresql+psycopg://trend_radar:trend_radar@127.0.0.1:5432/trend_radar'
uv run python scripts/evaluate.py daily --date 2026-09-20
uv run python scripts/evaluate.py weekly --week 1 --poc-start 2026-09-20
```

Reports are written through a flushed and fsynced sibling temporary file, then atomically replaced:

```text
reports/YYYY-MM-DD.md
reports/week-01.md
```

## Phase verification (2026-09-21)

- Evaluation/report/CLI focused suite: 14 passed.
- Real PostgreSQL daily report for 2026-09-20: official collection complete, 68 raw observations,
  seven unique candidates, zero trend entities, and zero approved cards.
- All categories had zero valid cards. Quality, cross-source, freshness, and cost-per-card
  denominators were unavailable and rendered `N/A`.
- Week 01 (`2026-09-20` through `2026-09-26`) aggregated the same facts but counted only one
  complete official-collection day.
- Collector/parser and all five pipeline version sets were emitted in the report.
