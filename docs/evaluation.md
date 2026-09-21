# Evaluation metrics and reports

Product analytics is a separate LIVE-only view and never changes the replayable Data PoC
evaluation. `DEMO` and `TEST` product cards, users, interactions, feedback, saves, and events are
excluded. Product rates use explicit feedback or interaction denominators; missing denominators are
unavailable, not zero. The internal category view reports discovery value and already-known rates
beside Data PoC usable/noise facts, but operators—not code—decide category status.

Category operations use a rolling 14-day LIVE window. Valid trends/day divides by all 14 calendar
days, including zero-result days. Automatic-pipeline and human-review agreement is card-based:
reviews retain the product card, snapshot, and category at review time, and repeated decisions use
the latest review per card. The view separately reports pipeline-publishable cards, policy shadow
eligibility, human-reviewed cards, and automatically publishable cards that received review.

Evaluation uses explicit UTC half-open periods (`start <= timestamp < end`). It computes facts from
stored official observations and append-only review history; it does not interpret a trend score as
a probability. Every zero denominator is rendered as `N/A`, never as `0%`.

## Daily formulas

| Metric | Definition |
|---|---|
| Raw candidates | Google Trends and Wikimedia source observations acquired during the UTC day |
| Unique entities | Distinct historically resolved entities linked to observations acquired that day |
| Source-day candidates | Diagnostic count linked to source timestamps; kept separate from acquisition supply |
| Trend entities | Distinct entities with a successful LIVE snapshot whose `as_of` is during the day |
| Approved cards | Entities reviewed that day whose final review state at period end is `APPROVE` |
| Category raw/entities | Acquisition-cohort observations and historically resolved entities by category |
| Category valid/usable | Final approved cards / latest human `VALID_TREND` adjudications; usable rate uses reviewed adjudications as denominator |
| Precision | `VALID_TREND / latest per-entity-and-actor human adjudications` |
| Duplicate rate | `DUPLICATE / latest per-entity-and-actor human adjudications` |
| Noise rate | `(TOO_OBVIOUS + NEWS_ONLY + NOT_USEFUL) / latest per-entity-and-actor adjudications` |
| Classification error rate | `WRONG_CATEGORY / latest per-entity-and-actor adjudications` |
| Merge error rate | `BAD_ENTITY_MERGE / latest per-entity-and-actor adjudications` |
| Unsupported summary rate | Non-publishable claims / all claims checked during the day |
| Cross-source rate | LIVE-snapshotted entities acquired from both sources that day / either source that day |
| Detection delay | First persisted `system_detected_at` minus first eligible official acquisition time |
| Approval delay | First approval time minus the entity's original detection time |
| Total cost | Stored amount plus `human_minutes / 60 * metadata_json.hourly_rate`, USD only |
| Cost per approved card | Total cost / approved cards |

Category is reconstructed from the last classification or audited `CHANGE_CATEGORY` action before
period end. Entity links are reconstructed from successful LIVE resolution attempts, followed by
MERGE/SPLIT reviews that existed before the cutoff; current mutable links cannot rewrite history.
A day is marked complete only when both Google Trends and Wikimedia have a successful acquisition
run that day. The scheduler refreshes D-2 after delayed Wikimedia arrives.

Freshness reports nearest-rank P50 and P95. Negative intervals are rejected as data integrity errors.
Mixed/non-USD cost records are rejected instead of being silently combined without exchange rates.
When no cost rows were collected, the report explicitly says `Cost data recorded: No` and renders
cost as `N/A`, not zero.

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

- Real PostgreSQL daily report for 2026-09-20 uses acquisition-day supply and separately shows the
  source-day diagnostic. Category supply/quality rows include zero denominators explicitly.
- All categories had zero valid cards. Quality, cross-source, freshness, and cost-per-card
  denominators were unavailable and rendered `N/A`.
- Week 01 (`2026-09-20` through `2026-09-26`) aggregated the same facts but counted only one
  complete official-collection day.
- Collector/parser and all five pipeline version sets were emitted in the report.
