# SoloPilot Daily Brief Quality Validation Design

**Status:** Approved design captured for implementation planning
**Date:** 2026-09-23
**Base:** `codex/geeknews-mini-pc-deploy` at `bc11c20`
**Implementation branch:** `codex/daily-brief-quality-validation`

## 1. Purpose

This cycle makes SoloPilot usable as a human-reviewed quality instrument for at least five distinct, healthy Daily Brief dates collected from real external sources. It records item-level judgments in PostgreSQL and produces derived Markdown and JSON reports centered on Useful Brief Rate.

The cycle does not add sources or user-facing product features. Review data is stored and analyzed only. It must not automatically alter ranking, clustering, personalization, prompts, source policy, or machine-learning behavior.

## 2. Success definition

The system succeeds when one reviewer can:

1. open each eligible published Daily Brief in the internal dashboard;
2. use `/today` as the real SoloPilot surface before opening the internal review workflow;
3. accumulate foreground-only active review time on the internal review screen;
4. review every BriefItem across the required quality dimensions;
5. record missing important events and structured duplicate/merge defects;
6. complete and lock the review session;
7. explicitly reopen a completed session with an actor, reason, and timestamp when correction is necessary; and
8. generate deterministic Markdown and JSON reports from PostgreSQL after at least five eligible dates are complete.

The validation cycle remains `IN_PROGRESS` until five eligible Brief dates have completed review sessions. Building the review tooling alone does not satisfy the five-day validation gate.

## 3. Scope

### In scope

- additive PostgreSQL schema and Alembic migration;
- internal FastAPI/Jinja reviewer workflow;
- foreground/visible active-review measurement;
- categorical BriefItem evaluation;
- structured duplicate, incorrect-merge, and missing-event provenance;
- daily and aggregate derived reports in Markdown and JSON;
- explicit inclusion/exclusion accounting for Brief dates;
- a runbook for collecting and reviewing at least five actual Brief dates;
- tests for persistence, locking, reporting, dashboard security, and migration.

### Out of scope

- new sources, X, arXiv, Hugging Face, or broad crawling;
- Radar enhancement, personalization, Ask SoloPilot, or BriefItem saving;
- automatic ranking changes, prompt optimization, recommendations, or ML training;
- automatically applying reviewer feedback to production behavior;
- fabricating historical Brief dates to satisfy the five-day gate;
- public Today feedback controls or public reviewer APIs.

## 4. Product metric

The primary metric keeps the approved product definition:

```text
Useful Brief Rate = BriefItems marked USEFUL / completed BriefItem reviews
```

It is an item-level rate. For example, five `USEFUL` judgments among six completed BriefItem reviews produce `83.33%`. A Brief date with no reviewable items has no Useful Brief Rate denominator and cannot count toward the five eligible dates.

The report must show numerator, denominator, and rate. It must never convert a missing denominator into zero.

## 5. Categorical evaluation contracts

All categorical values are closed enums stored as strings. Reports must preserve the raw category counts and may derive rates or ordinal summaries without replacing the original judgments.

### `BriefItemUsefulness`

- `USEFUL`
- `NOT_USEFUL`

### `EventSelectionVerdict`

- `KEEP`
- `SHOULD_EXCLUDE`
- `UNSURE`

### `FactCorrectness`

- `CORRECT`
- `PARTIALLY_CORRECT`
- `INCORRECT`
- `UNVERIFIABLE`

### `InterpretationQuality`

- `STRONG`
- `ACCEPTABLE`
- `WEAK`
- `MISLEADING`

### `WatchUsefulness`

- `ACTIONABLE`
- `USEFUL`
- `GENERIC`
- `NOT_USEFUL`

### `VerbosityVerdict`

- `TOO_SHORT`
- `JUST_RIGHT`
- `TOO_LONG`

### `EvidenceSetUsefulness`

- `ESSENTIAL`
- `HELPFUL`
- `REDUNDANT`
- `NOT_USEFUL`

This category evaluates whether the BriefItem's complete displayed evidence/link set is useful for checking the item. It does not score individual sources. Per-source usefulness requires a separate future model and is out of scope.

### `IncorrectMergeVerdict`

- `NO_INCORRECT_MERGE`
- `INCORRECT_MERGE`
- `UNSURE`

### `DuplicateEscapeVerdict`

- `NO_DUPLICATE_ESCAPE`
- `DUPLICATE_ESCAPE`
- `UNSURE`

## 6. PostgreSQL source-of-truth model

PostgreSQL review rows are the sole source of truth. Markdown and JSON are disposable derived artifacts and must be reproducible from database state.

### `brief_review_sessions`

One session represents one reviewer evaluating one immutable DailyBrief version.

Required fields:

- `id`
- `brief_id` foreign key to `daily_briefs`
- `reviewer`
- `status`: `OPEN` or `COMPLETED`
- `started_at`
- `completed_at`, nullable until completion
- `completion_revision`, starting at zero and incremented on every completion
- `missing_events_confirmed`: explicit boolean proving the reviewer considered omissions
- `overall_notes`, nullable
- `created_at`
- `updated_at`

`(brief_id, reviewer)` is unique. Review sessions target a specific Brief version through `brief_id`; a later Brief version gets a separate session.

### `brief_review_reopens`

Every transition from `COMPLETED` back to `OPEN` appends an audit row:

- `id`
- `session_id`
- `actor`
- `reason`, required and non-blank
- `reopened_at`
- `previous_completed_at`
- `previous_completion_revision`

Completed sessions reject activity pulses, item edits, missing-event edits, and note edits. Reopening must lock the session row, append the audit record, clear `completed_at`, change status to `OPEN`, and preserve the previous review data for correction. There is no silent mutation path.

### `brief_review_activity_pulses`

Active review time is derived from append-only foreground pulses rather than `completed_at - started_at`.

Fields:

- `id`
- `session_id`
- `client_event_id`, unique within the session
- `active_seconds`, integer from 1 through 30
- `recorded_at`

The browser records a pulse only while the review page is visible and the window has focus. It flushes the accumulated visible interval on blur, visibility change, form submit, navigation, or every 15 seconds. Replayed `client_event_id` values are idempotent. The core review-effort metric is:

```text
active_review_seconds = SUM(brief_review_activity_pulses.active_seconds)
```

This measures time spent actively evaluating the Brief in the internal review dashboard. It is not `/today` reading time and must not be labeled or interpreted as actual product reading time. Wall-clock session duration is diagnostic only. Measuring actual `/today` reading time requires a separate future dogfood telemetry design.

### `brief_item_reviews`

Each BriefItem must have exactly one current review in its session.

Fields:

- `id`
- `session_id`
- `brief_item_id`
- all enums from section 5;
- `duplicate_of_brief_item_id`, nullable;
- `duplicate_of_event_cluster_id`, nullable;
- `notes`, nullable;
- `created_at`
- `updated_at`

`(session_id, brief_item_id)` is unique. The service verifies that the BriefItem belongs to the session's Brief.

When `duplicate_escape_verdict` is `DUPLICATE_ESCAPE`, at least one structured target is required: another BriefItem or an EventCluster. A duplicate BriefItem must belong to the same Brief and cannot reference itself. An EventCluster target may represent a known duplicate outside the Brief.

### `brief_item_review_merge_memberships`

Incorrect merge review must identify the exact persisted membership under dispute.

Fields:

- `brief_item_review_id`
- `event_cluster_item_id` foreign key to `event_cluster_items`
- `reason`, nullable

When `incorrect_merge_verdict` is `INCORRECT_MERGE`, at least one membership from the BriefItem's EventCluster is required. Memberships from other clusters are rejected. This preserves the cluster, RawItem membership, and assignment provenance needed for later diagnosis.

### `missing_event_reviews`

Missing important events are session-level because no BriefItem exists for them.

Fields:

- `id`
- `session_id`
- `canonical_title`
- `canonical_url`, required HTTPS URL after canonicalization
- `discovered_from` using `MissingEventDiscoverySource`
- `reason`
- `created_at`
- `updated_at`

`(session_id, canonical_url)` is unique. Completing a session requires `missing_events_confirmed=true`, even when the missing-event list is empty.

`MissingEventDiscoverySource` is independent of the collector `Source` and `SourceType` enums so unsupported discovery channels can be recorded without enabling a collector. Its categories are:

- `GEEKNEWS`
- `HACKER_NEWS`
- `GITHUB`
- `OFFICIAL_WEB`
- `X`
- `ARXIV`
- `HUGGING_FACE`
- `REDDIT`
- `OTHER`

Recording one of these values is observational only. It must not enable, schedule, or implement the corresponding source.

## 7. Session state and write rules

All writes go through `BriefQualityReviewService` and occur transactionally.

- Creating a session is idempotent for `(brief_id, reviewer)`.
- Only `PUBLISHED` Briefs are reviewable for the five-day gate.
- Item and missing-event writes lock and re-read the session.
- Writes to `COMPLETED` sessions return a conflict and do not mutate data.
- Completion requires a review for every BriefItem, explicit missing-event confirmation, and at least one active review pulse.
- Completion sets `completed_at`, increments `completion_revision`, and changes status to `COMPLETED` in one transaction.
- Reopen requires a non-blank reason and actor, appends its audit row, and changes the session back to `OPEN` in one transaction.
- A reopened session must pass all completion checks again before it can be completed.

No review write mutates `DailyBrief`, `BriefItem`, `EventCluster`, `EventAssessment`, ranking output, or public user data.

## 8. Internal reviewer workflow

The existing protected FastAPI/Jinja dashboard is extended; no public route is added.

### List screen

`GET /internal/brief-quality` shows:

- published Brief dates and versions;
- item count and estimated reading time;
- source-coverage/publication status;
- reviewer session state;
- reviewed item count;
- foreground active review time;
- eligibility and exclusion reason.

### Review screen

`GET /internal/briefs/{brief_id}/quality-review` shows the immutable Brief snapshot, sources, FACT/INTERPRETATION/WATCH sections, and categorical controls for every BriefItem. It also provides missing-event inputs, active-review status, and completion controls.

This screen is not the SoloPilot consumption surface. The documented daily workflow requires the reviewer to use `/today` first, then open the internal screen to evaluate what they already consumed. The review screen may link back to `/today`, but it must not present itself as a substitute for the Today experience.

### Write routes

- `POST /internal/briefs/{brief_id}/quality-review/start`
- `POST /internal/brief-review-sessions/{session_id}/activity-pulses`
- `POST /internal/brief-review-sessions/{session_id}/items/{brief_item_id}`
- `POST /internal/brief-review-sessions/{session_id}/missing-events`
- `POST /internal/brief-review-sessions/{session_id}/complete`
- `POST /internal/brief-review-sessions/{session_id}/reopen`

The existing dashboard access policy, same-origin browser behavior, escaping rules, and public-host API-key requirements remain in force. Canonical URLs are rendered as external links but are never fetched by the dashboard.

## 9. Date eligibility and operating gate

Eligibility is anchored to the latest `PUBLISHED` DailyBrief version for each date, ordered by version. An older reviewed version never substitutes for a newer published version.

An included validation date must satisfy all of the following:

1. the reviewed target is the latest `PUBLISHED` DailyBrief version for the date;
2. the Brief contains at least one BriefItem;
3. the source coverage gate passed when the Brief was published;
4. the requested reviewer has a `COMPLETED` session for that exact latest published Brief version;
5. every BriefItem has a complete item review;
6. missing events were explicitly considered; and
7. active review time is greater than zero.

If the latest published version is unreviewed, the date is excluded with `LATEST_PUBLISHED_VERSION_UNREVIEWED`; the report must not fall back to an older completed review. Superseded versions are listed as excluded provenance.

`LOW_SIGNAL_DAY`, `DEGRADED_SOURCE_COVERAGE`, `REJECTED`, and `DRAFT` dates do not count toward the five-date quality denominator. They remain visible in the report's operational-date and excluded-date sections with a reason. In particular, every `LOW_SIGNAL_DAY` during the dogfood period is included in the operational record even though it cannot satisfy an item-review denominator.

The aggregate sample status is:

- `VALIDATION_SAMPLE_COMPLETE` when at least five distinct eligible dates are included;
- `INSUFFICIENT_VALIDATION_DAYS` otherwise.

`VALIDATION_SAMPLE_COMPLETE` means only that the minimum evaluation sample exists. It is not a quality pass, launch decision, or ranking approval. The report generator may render partial daily diagnostics before five days, but it must not label the validation cycle or product quality successful.

## 10. Derived quality report

`scripts/evaluate_brief_quality.py` requires `--reviewer`, `--start-date`, and `--end-date`, reads PostgreSQL, and writes both files atomically:

- `reports/brief-quality-<start>-<end>.json`
- `reports/brief-quality-<start>-<end>.md`

The JSON representation is the canonical derived report shape; Markdown renders that shape without recomputing metrics. Neither artifact is read back as evaluation input.

Only completed sessions for the requested reviewer contribute metrics or eligibility. Other reviewers remain stored for independent comparison but cannot be silently mixed into the denominator.

Required metadata:

- report schema/version;
- intelligence pipeline version stored on the Brief;
- distinct clustering versions;
- distinct assessment versions;
- generation versions;
- requested date range;
- included Brief dates and IDs;
- excluded Brief dates, IDs, statuses, and exclusion reasons;
- generated timestamp and reviewer identities.

Required metrics:

- Useful Brief Rate numerator, denominator, and rate;
- event-selection verdict distribution;
- missing important events per day and `MissingEventDiscoverySource` distribution;
- incorrect merge count/rate and linked membership IDs;
- duplicate escape count/rate and linked item/event targets;
- Fact correctness distribution;
- Interpretation quality distribution;
- Watch usefulness distribution;
- Verbosity distribution;
- Evidence-set usefulness distribution;
- active review time per day plus P50/P95, explicitly labeled as review effort rather than product reading time;
- reviewed Brief/date/item counts.

Rates use completed item reviews as their denominator unless the metric definition states otherwise. Reports display `N/A` for zero denominators.

## 11. Version provenance

The additive migration adds `pipeline_version` to `daily_briefs`. New Brief generation writes an explicit stable version such as `intelligence-pipeline-v1`; existing Briefs are backfilled with `intelligence-pipeline-v1` because they were generated by the completed First Slice pipeline.

The report reads:

- `DailyBrief.pipeline_version`;
- `DailyBrief.generation_version`;
- `EventCluster.clustering_version` for selected BriefItems;
- `EventAssessment.assessment_version` for selected BriefItems; and
- a report schema constant such as `brief-quality-report-v1`.

The report must not infer or invent missing versions. Missing version provenance excludes the affected date with `MISSING_VERSION_PROVENANCE`.

## 12. Five-day operation

The production collector, processing, generation, and publication schedule remains unchanged. The operator performs the following for at least five eligible actual dates:

1. allow the existing scheduler to collect real external data and publish the Daily Brief;
2. verify source coverage is healthy;
3. use `/today` as the real product experience before reviewing;
4. open the internal quality-review screen and accumulate active review time;
5. review every BriefItem and record any missing event;
6. complete the session; and
7. generate the partial report to see remaining eligible days.

No historical fixture, copied Brief, manually altered publication status, or future-clock run counts toward the five actual dates.

All Brief dates encountered during the dogfood period, including `LOW_SIGNAL_DAY`, are retained in the operational record. Only dates satisfying the stricter eligibility contract contribute to the five-date denominator.

## 13. Error handling and integrity

- Invalid enum values return validation errors and persist nothing.
- Duplicate targets and incorrect-merge memberships are validated structurally before commit.
- Activity pulses above 30 seconds, non-positive pulses, or duplicate event IDs are rejected or treated idempotently as specified.
- Concurrent completion/reopen/edit attempts use row locking; a stale completed-state write returns conflict.
- Deleting a Brief with review history is prohibited by foreign keys.
- Report generation uses a consistent database snapshot so included dates and metrics cannot drift during rendering.
- Atomic file replacement prevents partial Markdown or JSON artifacts.
- Database and report timestamps are timezone-aware; Brief eligibility uses the existing Asia/Seoul Brief date.

## 14. Testing strategy

### Model and migration

- fresh `0012` apply and downgrade/upgrade checks;
- upgrade from `0011` preserves existing First Slice rows;
- enum, uniqueness, foreign-key, and target constraints;
- pipeline-version backfill.

### Service

- completed sessions reject silent edits;
- reopen requires and records actor, reason, timestamp, and prior completion;
- foreground pulse replay is idempotent and active review seconds are summed;
- completion rejects missing item reviews, missing omission confirmation, or zero active time;
- duplicate targets and incorrect-merge memberships enforce cluster ownership;
- reviewer writes never alter ranking, Brief, cluster, or assessment outputs.

### Dashboard

- list and review screens render escaped persisted data;
- categorical forms round-trip;
- visibility/focus timer sends only bounded active review intervals;
- completed sessions expose reopen rather than edit controls;
- dashboard access/security behavior remains unchanged.

### Reports

- Useful Brief Rate uses the approved item denominator;
- all categorical distributions and active-review percentiles are deterministic;
- included/excluded dates and all version fields are emitted in JSON and Markdown;
- fewer than five eligible dates yields `INSUFFICIENT_VALIDATION_DAYS`;
- five eligible dates yields `VALIDATION_SAMPLE_COMPLETE` without implying a quality pass;
- zero denominators render `N/A` rather than zero;
- Markdown is a rendering of the JSON report model.

### Regression

- full backend suite;
- PostgreSQL integration and migration tests;
- dashboard security tests;
- frontend tests, lint, typecheck, and production build.

## 15. Exit criteria

Implementation is ready for field use when schema, dashboard, service, CLI, and report tests pass. The quality-validation cycle itself completes only after:

- at least five eligible real external-data Brief dates;
- every included BriefItem reviewed by a human;
- active review time captured for every included date and never reported as actual `/today` reading time;
- missing important events explicitly assessed;
- PostgreSQL review records retained as source of truth;
- a `VALIDATION_SAMPLE_COMPLETE` Markdown and JSON report generated with all required metrics and provenance; and
- no automatic ranking, personalization, or ML feedback path exists.
