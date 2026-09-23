# Daily Brief Quality Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PostgreSQL-backed, human review workflow and deterministic quality report so SoloPilot can be dogfooded through `/today` and then evaluated across at least five real published Daily Brief dates without feeding judgments back into production behavior.

**Architecture:** Extend the existing additive SQLAlchemy/Alembic schema with immutable-after-completion review records, expose those records only through the protected FastAPI/Jinja internal dashboard, and derive one canonical JSON report model plus a Markdown rendering from a repeatable database snapshot. Keep `/today` as the product consumption surface; the internal screen measures `active_review_seconds`, not product reading time. Keep all review writes isolated from collection, clustering, assessment, ranking, generation, and personalization paths.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLAlchemy 2, Alembic, PostgreSQL, pytest, vanilla browser JavaScript, Ruff

**Spec:** `docs/superpowers/specs/2026-09-23-daily-brief-quality-validation-design.md`

## Global Constraints

- PostgreSQL review tables are the source of truth; generated JSON and Markdown are disposable derived artifacts.
- Only the latest `PUBLISHED` DailyBrief version for a date can become eligible. Never fall back to an older reviewed version.
- `VALIDATION_SAMPLE_COMPLETE` means five eligible dates exist; it is not a quality pass.
- `LOW_SIGNAL_DAY` is excluded from the quality denominator but included in the dogfood operational record.
- `active_review_seconds` measures foreground time on the internal review page and must never be labeled as `/today` reading time.
- `MissingEventDiscoverySource` is independent of collector `Source` and `SourceType`.
- `EvidenceSetUsefulness` evaluates the complete evidence/link set, not individual sources.
- No review result may mutate or automatically influence collection, clustering, assessment, ranking, generation, personalization, or ML behavior.
- Do not add sources, X/arXiv/Hugging Face collectors, Radar enhancements, personalization, Ask SoloPilot, or BriefItem saving.
- Do not fabricate historical/future Brief dates to satisfy the five-day operational gate.

## Review Focus

- Transactional state transitions and immutability after completion.
- Foreign-key ownership checks for duplicate and incorrect-merge targets.
- Latest-published-version eligibility and complete exclusion provenance.
- Deterministic metrics, version provenance, and identical JSON/Markdown meaning.
- Dashboard access controls, output escaping, same-origin writes, and bounded/idempotent activity pulses.
- Upgrade safety from `0011`, downgrade behavior, and retention of existing First Slice rows.

---

### Task 1: Add review enums and persistence models

**Files:**

- Modify: `app/models/enums.py`
- Modify: `app/models/tables.py`
- Create: `tests/models/test_brief_quality_schema.py`

- [ ] **Step 1: Write failing enum and table-contract tests**

  Add tests asserting the exact values of `BriefReviewSessionStatus`, `BriefItemUsefulness`, `EventSelectionVerdict`, `FactCorrectness`, `InterpretationQuality`, `WatchUsefulness`, `VerbosityVerdict`, `EvidenceSetUsefulness`, `IncorrectMergeVerdict`, `DuplicateEscapeVerdict`, and independent `MissingEventDiscoverySource`. Assert the six review tables, required columns, unique constraints, check constraints, and foreign keys appear in `Base.metadata`.

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `uv run pytest tests/models/test_brief_quality_schema.py -q`

  Expected: import or metadata assertion failures because the enums and tables do not exist.

- [ ] **Step 3: Implement the smallest model layer**

  Add the approved `StrEnum` classes. Add `BriefReviewSession`, `BriefReviewReopen`, `BriefReviewActivityPulse`, `BriefItemReview`, `BriefItemReviewMergeMembership`, and `MissingEventReview` with:

  - string-backed enums via the existing `enum_column` helper;
  - `(brief_id, reviewer)`, `(session_id, client_event_id)`, `(session_id, brief_item_id)`, `(brief_item_review_id, event_cluster_item_id)`, and `(session_id, canonical_url)` uniqueness;
  - `1 <= active_seconds <= 30` database check;
  - `ON DELETE RESTRICT` semantics on DailyBrief/BriefItem/EventCluster/EventClusterItem history links and `ON DELETE CASCADE` only from a review session to its owned pulses/reopens/missing rows and from an item review to its membership links;
  - timezone-aware timestamps and `completion_revision` defaulting to zero.

- [ ] **Step 4: Run focused schema tests and model regression**

  Run: `uv run pytest tests/models/test_brief_quality_schema.py tests/models/test_intelligence_schema.py tests/models/test_schema.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add app/models/enums.py app/models/tables.py tests/models/test_brief_quality_schema.py
  git commit -m "feat: add brief quality review models"
  ```

### Task 2: Add migration 0012 and Brief pipeline provenance

**Files:**

- Create: `alembic/versions/0012_daily_brief_quality_review.py`
- Modify: `app/models/tables.py`
- Modify: `app/services/daily_brief.py`
- Create: `tests/integration/test_migration_0012.py`
- Modify: `tests/services/test_daily_brief.py`

- [ ] **Step 1: Write failing migration and service tests**

  Add PostgreSQL migration coverage that starts at `0011` with a real DailyBrief row, upgrades to `0012`, verifies the row is preserved and `pipeline_version='intelligence-pipeline-v1'`, verifies every review table/index/constraint, downgrades to `0011`, and upgrades to head again. Add service tests asserting newly generated Briefs store an explicit pipeline version.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `uv run pytest tests/services/test_daily_brief.py -q`

  With `TEST_MIGRATION_DATABASE_URL` configured, also run: `uv run pytest tests/integration/test_migration_0012.py -q`

  Expected: failures because `pipeline_version` and revision `0012` do not exist.

- [ ] **Step 3: Implement the additive migration**

  Create revision `0012` over `0011`. Add non-null `daily_briefs.pipeline_version` using a temporary server default of `intelligence-pipeline-v1`, backfill existing rows, then remove the server default so new writes must be explicit. Create the review tables in dependency order with named constraints and indexes. Downgrade drops review tables in reverse dependency order and then drops `pipeline_version`, leaving all `0011` data intact.

- [ ] **Step 4: Write explicit pipeline provenance on generation**

  Add a stable `INTELLIGENCE_PIPELINE_VERSION = "intelligence-pipeline-v1"` constant in `app/services/daily_brief.py` and set `DailyBrief.pipeline_version` for every newly generated Brief.

- [ ] **Step 5: Run focused and migration tests**

  Run: `uv run pytest tests/services/test_daily_brief.py tests/models/test_brief_quality_schema.py -q`

  With PostgreSQL configured: `uv run pytest tests/integration/test_migration_0012.py -q`

  Expected: PASS, including upgrade/downgrade/re-upgrade.

- [ ] **Step 6: Commit**

  ```bash
  git add alembic/versions/0012_daily_brief_quality_review.py app/models/tables.py app/services/daily_brief.py tests/integration/test_migration_0012.py tests/services/test_daily_brief.py
  git commit -m "feat: migrate brief quality review storage"
  ```

### Task 3: Implement transactional session lifecycle and activity tracking

**Files:**

- Create: `app/services/brief_quality_review.py`
- Create: `tests/services/test_brief_quality_review.py`

- [ ] **Step 1: Write failing lifecycle tests**

  Cover idempotent `start_session(brief_id, reviewer)`, rejection of non-`PUBLISHED` Briefs, idempotent `(session_id, client_event_id)` pulses, the `1..30` second boundary, summed `active_review_seconds`, completion prerequisites, completion revision increments, completed-session mutation conflicts, and explicit reopen audit fields (`actor`, `reason`, `reopened_at`, prior timestamp/revision).

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `uv run pytest tests/services/test_brief_quality_review.py -q`

  Expected: import failure for `BriefQualityReviewService`.

- [ ] **Step 3: Implement lifecycle methods**

  Implement `start_session`, `record_activity_pulse`, `set_missing_events_confirmed`, `update_overall_notes`, `complete_session`, `reopen_session`, and `active_review_seconds`. Every mutating method must load the session with `SELECT ... FOR UPDATE`, reject edits while `COMPLETED`, use caller-provided timezone-aware `now` values for deterministic tests, and flush without committing so the request/session boundary owns the transaction.

- [ ] **Step 4: Make pulse replay idempotent under concurrency**

  Check an existing event ID before insert and retain the database unique constraint as the race backstop. Convert the duplicate-key race into a successful no-op without increasing active seconds; do not mask unrelated integrity errors.

- [ ] **Step 5: Run lifecycle tests**

  Run: `uv run pytest tests/services/test_brief_quality_review.py -q`

  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add app/services/brief_quality_review.py tests/services/test_brief_quality_review.py
  git commit -m "feat: enforce brief review lifecycle"
  ```

### Task 4: Implement categorical item reviews and structured defect provenance

**Files:**

- Modify: `app/services/brief_quality_review.py`
- Modify: `tests/services/test_brief_quality_review.py`

- [ ] **Step 1: Write failing item and missing-event tests**

  Cover full categorical upsert, BriefItem ownership, independent `MissingEventDiscoverySource`, HTTPS URL canonicalization, missing-event uniqueness, duplicate escape requiring a target, same-Brief/non-self duplicate item rules, external EventCluster duplicate targets, incorrect merge requiring at least one exact membership, and rejection of memberships from another cluster. Snapshot production Brief/cluster/assessment rows before review writes and assert they remain byte-for-byte unchanged afterward.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `uv run pytest tests/services/test_brief_quality_review.py -q`

  Expected: failures for unimplemented item and missing-event operations.

- [ ] **Step 3: Implement validated write DTOs and service methods**

  Add frozen input dataclasses for item review and missing event data. Implement `upsert_item_review`, `replace_incorrect_merge_memberships`, `add_missing_event`, and `delete_missing_event`. Validate all structural ownership before any write, normalize HTTPS URLs without fetching them, and persist all membership replacements in the session transaction.

- [ ] **Step 4: Tighten completion validation**

  Require exactly one complete review for every BriefItem, `missing_events_confirmed=true`, and positive summed active review time. Re-run these checks after every reopen before completing again.

- [ ] **Step 5: Run service and schema regression**

  Run: `uv run pytest tests/services/test_brief_quality_review.py tests/models/test_brief_quality_schema.py -q`

  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add app/services/brief_quality_review.py tests/services/test_brief_quality_review.py
  git commit -m "feat: capture structured brief quality judgments"
  ```

### Task 5: Add protected internal quality-review routes

**Files:**

- Create: `app/api/brief_quality.py`
- Modify: `app/main.py`
- Create: `tests/api/test_brief_quality.py`
- Modify: `tests/config/test_dashboard_security.py`

- [ ] **Step 1: Write failing route tests**

  Test `GET /internal/brief-quality`, `GET /internal/briefs/{brief_id}/quality-review`, and all six approved POST operations. Assert enum/form validation, 404 ownership failures, 409 completed-session conflicts, redirect-after-write behavior, API-key protection on public binds, same-origin form behavior, and that a latest unreviewed published version is labeled `LATEST_PUBLISHED_VERSION_UNREVIEWED` instead of falling back.

- [ ] **Step 2: Run focused API tests and verify RED**

  Run: `uv run pytest tests/api/test_brief_quality.py tests/config/test_dashboard_security.py -q`

  Expected: 404/import failures because the router is absent.

- [ ] **Step 3: Implement request parsing and route adapters**

  Add a protected `/internal` router using existing `require_dashboard_access` and `get_db` dependencies. Keep business validation in `BriefQualityReviewService`; map not-found to 404, invalid state/ownership to 409 or 422, and use 303 redirects after successful HTML form submissions. Add `POST /internal/brief-review-sessions/{session_id}/activity-pulses` as JSON or form input with a stable client event ID.

- [ ] **Step 4: Register the router without adding a public API**

  Include only the new internal router in `app/main.py`. Do not change `/api/public/today` or add review fields to public responses.

- [ ] **Step 5: Run API and security tests**

  Run: `uv run pytest tests/api/test_brief_quality.py tests/config/test_dashboard_security.py tests/api/test_today.py -q`

  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add app/api/brief_quality.py app/main.py tests/api/test_brief_quality.py tests/config/test_dashboard_security.py
  git commit -m "feat: expose protected brief quality review routes"
  ```

### Task 6: Build the Jinja reviewer workflow and active-review timer

**Files:**

- Create: `dashboard/templates/brief_quality.html`
- Create: `dashboard/templates/brief_quality_review.html`
- Create: `dashboard/static/brief_quality.js`
- Modify: `dashboard/templates/base.html`
- Modify: `dashboard/static/styles.css`
- Modify: `tests/api/test_brief_quality.py`
- Create: `tests/api/test_brief_quality_timer.py`

- [ ] **Step 1: Write failing rendering and static-contract tests**

  Assert the list shows Brief date/version/status, item count, estimated reading time, review state/count, active review time, and exclusion reason. Assert the review page links to `/today` first, labels time as review effort, renders escaped Brief/source data, exposes all categorical controls, shows edit controls only for `OPEN`, and shows explicit reopen controls for `COMPLETED`. Test the timer source for focus/visibility gating, 15-second periodic flush, 30-second maximum payload, and flush on blur/navigation/form submit.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `uv run pytest tests/api/test_brief_quality.py tests/api/test_brief_quality_timer.py -q`

  Expected: template/static-file failures.

- [ ] **Step 3: Implement list and review templates**

  Render immutable Brief snapshot content, source links, FACT/INTERPRETATION/WATCH, item forms, structured duplicate and membership choices, missing-event forms, confirmation/notes controls, completion status, and reopen audit history. Add a prominent `/today` link and language that the reviewer must consume Today first. Never label the internal page as the product reading surface.

- [ ] **Step 4: Implement bounded foreground activity pulses**

  In `brief_quality.js`, accumulate seconds only when `document.visibilityState === 'visible'` and `document.hasFocus()`. Flush at 15 seconds and lifecycle boundaries, cap each event at 30 seconds, use a collision-resistant client event ID, retain failed unsent seconds for retry, and stop sending once the session is completed.

- [ ] **Step 5: Add minimal dashboard styling and navigation**

  Extend the existing dashboard styles and add one navigation entry. Avoid redesigning `/today` or the internal dashboard.

- [ ] **Step 6: Run dashboard/API regression**

  Run: `uv run pytest tests/api/test_brief_quality.py tests/api/test_brief_quality_timer.py tests/api/test_dashboard.py tests/config/test_dashboard_security.py -q`

  Expected: PASS.

- [ ] **Step 7: Commit**

  ```bash
  git add dashboard/templates/brief_quality.html dashboard/templates/brief_quality_review.html dashboard/static/brief_quality.js dashboard/templates/base.html dashboard/static/styles.css tests/api/test_brief_quality.py tests/api/test_brief_quality_timer.py
  git commit -m "feat: add brief quality review dashboard"
  ```

### Task 7: Build the canonical quality report model and eligibility evaluator

**Files:**

- Create: `app/evaluation/brief_quality_models.py`
- Create: `app/evaluation/brief_quality_database.py`
- Create: `app/evaluation/brief_quality_metrics.py`
- Create: `tests/evaluation/test_brief_quality_database.py`
- Create: `tests/evaluation/test_brief_quality_metrics.py`

- [ ] **Step 1: Write failing eligibility tests**

  Cover latest `PUBLISHED` selection by date/version, `LATEST_PUBLISHED_VERSION_UNREVIEWED`, superseded reviewed-version provenance, incomplete review reasons, zero activity, empty items, missing version provenance, `LOW_SIGNAL_DAY` operational inclusion, degraded/rejected/draft exclusions, requested-reviewer isolation, and Asia/Seoul date boundaries.

- [ ] **Step 2: Write failing metric tests**

  Cover Useful Brief Rate numerator/denominator/rate, all enum distributions, missing event counts and discovery-source distribution, structured incorrect-merge and duplicate-escape links, daily active review seconds, deterministic P50/P95, zero-denominator `None`, and five distinct eligible dates producing `VALIDATION_SAMPLE_COMPLETE` rather than a quality judgment.

- [ ] **Step 3: Run focused tests and verify RED**

  Run: `uv run pytest tests/evaluation/test_brief_quality_database.py tests/evaluation/test_brief_quality_metrics.py -q`

  Expected: import failures for the new modules.

- [ ] **Step 4: Implement immutable report dataclasses**

  Define the canonical report shape: metadata/version sets, operational dates, included dates, excluded dates/reasons, defect link records, categorical distributions, rate values, active-review summaries, counts, and sample status. Preserve `None` for rates with no denominator.

- [ ] **Step 5: Implement one database snapshot loader**

  Load the requested range and reviewer in a consistent transaction snapshot. Select the latest `PUBLISHED` version independently from review existence; enumerate non-published operational rows including all `LOW_SIGNAL_DAY` dates; collect exact pipeline/generation/clustering/assessment versions; and return normalized facts without calculating presentation text.

- [ ] **Step 6: Implement pure deterministic aggregation**

  Aggregate normalized facts into the canonical report dataclass. Sort dates, IDs, distributions, and version sets deterministically. Set `VALIDATION_SAMPLE_COMPLETE` only at five included dates; do not emit pass/fail quality language.

- [ ] **Step 7: Run evaluation tests**

  Run: `uv run pytest tests/evaluation/test_brief_quality_database.py tests/evaluation/test_brief_quality_metrics.py -q`

  Expected: PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add app/evaluation/brief_quality_models.py app/evaluation/brief_quality_database.py app/evaluation/brief_quality_metrics.py tests/evaluation/test_brief_quality_database.py tests/evaluation/test_brief_quality_metrics.py
  git commit -m "feat: evaluate daily brief quality samples"
  ```

### Task 8: Generate atomic JSON and Markdown derived reports

**Files:**

- Create: `app/evaluation/brief_quality_reports.py`
- Create: `scripts/evaluate_brief_quality.py`
- Create: `tests/evaluation/test_brief_quality_reports.py`
- Create: `tests/scripts/test_evaluate_brief_quality_cli.py`

- [ ] **Step 1: Write failing renderer tests**

  Assert canonical JSON includes report/pipeline/clustering/assessment/generation versions, reviewer/date range, included and excluded Brief IDs/dates, operational `LOW_SIGNAL_DAY` rows, every metric, generated timestamp, and sample status. Assert Markdown renders only the canonical model, labels `active_review_seconds` as review effort, includes `N/A`, and never uses quality-pass wording.

- [ ] **Step 2: Write failing CLI and atomic-write tests**

  Require `--reviewer`, `--start-date`, and `--end-date`; reject reversed ranges; assert exact filenames; assert both artifacts use temporary-file replacement; and simulate a write failure to prove no partial target replaces a prior valid report.

- [ ] **Step 3: Run focused tests and verify RED**

  Run: `uv run pytest tests/evaluation/test_brief_quality_reports.py tests/scripts/test_evaluate_brief_quality_cli.py -q`

  Expected: import failures for renderer and CLI.

- [ ] **Step 4: Implement canonical serialization and Markdown rendering**

  Serialize the report dataclass to stable, UTF-8, indented JSON with ISO timestamps and sorted keys. Render Markdown from that serialized model or the same immutable dataclass only; do not query the database or recompute metrics in the renderer.

- [ ] **Step 5: Implement the CLI transaction and paired atomic outputs**

  Open the database session, establish a repeatable-read transaction on PostgreSQL, build one report model, then atomically replace the JSON and Markdown targets. If either temporary render/write fails, preserve existing target files and clean temporary files.

- [ ] **Step 6: Run report/CLI tests**

  Run: `uv run pytest tests/evaluation/test_brief_quality_reports.py tests/scripts/test_evaluate_brief_quality_cli.py -q`

  Expected: PASS.

- [ ] **Step 7: Commit**

  ```bash
  git add app/evaluation/brief_quality_reports.py scripts/evaluate_brief_quality.py tests/evaluation/test_brief_quality_reports.py tests/scripts/test_evaluate_brief_quality_cli.py
  git commit -m "feat: generate brief quality validation reports"
  ```

### Task 9: Add PostgreSQL integrity and concurrency coverage

**Files:**

- Create: `tests/integration/test_brief_quality_postgres.py`
- Modify: `tests/integration/test_migration_0012.py`

- [ ] **Step 1: Write PostgreSQL-only failing tests**

  Use two independent sessions to test simultaneous pulse replay, completion versus item edit, and reopen versus edit. Verify exact unique/check/foreign-key behavior, row-lock serialization, immutable completed state, retained reopen history, and successful persistence across a fresh SQLAlchemy engine restart.

- [ ] **Step 2: Run against configured PostgreSQL and verify RED where behavior is incomplete**

  Run: `uv run pytest tests/integration/test_brief_quality_postgres.py tests/integration/test_migration_0012.py -q`

- [ ] **Step 3: Fix only demonstrated PostgreSQL gaps**

  Adjust transaction boundaries, constraint names, locking queries, or narrow exception handling in the migration/models/service. Do not weaken ownership validation or add SQLite-only workarounds.

- [ ] **Step 4: Re-run PostgreSQL integration tests**

  Run: `uv run pytest tests/integration/test_brief_quality_postgres.py tests/integration/test_migration_0012.py -q`

  Expected: PASS with a real PostgreSQL URL; otherwise record the tests as environment-skipped and do not claim production persistence validation.

- [ ] **Step 5: Commit**

  ```bash
  git add tests/integration/test_brief_quality_postgres.py tests/integration/test_migration_0012.py app/services/brief_quality_review.py app/models/tables.py alembic/versions/0012_daily_brief_quality_review.py
  git commit -m "test: verify brief quality persistence on postgres"
  ```

### Task 10: Document the five-day dogfood operation

**Files:**

- Create: `docs/it-intelligence/daily-brief-quality-validation.md`
- Modify: `docs/it-intelligence/implementation-progress.md`
- Create: `tests/docs/test_brief_quality_runbook.py`

- [ ] **Step 1: Write a failing documentation contract test**

  Assert the runbook names `/today` as step one, the internal review as step two, `active_review_seconds` as review effort, latest-published eligibility, the low-signal operational record, report commands, PostgreSQL source-of-truth, the five-real-date rule, and prohibited automatic feedback/features.

- [ ] **Step 2: Run the documentation test and verify RED**

  Run: `uv run pytest tests/docs/test_brief_quality_runbook.py -q`

  Expected: failure because the runbook is absent.

- [ ] **Step 3: Write the operator runbook**

  Document daily collection/source-health checks, `/today` consumption, internal evaluation, explicit completion/reopen, partial report generation, interpreting exclusion reasons, backing up PostgreSQL, and determining when `VALIDATION_SAMPLE_COMPLETE` is reached. State that implementation readiness does not complete the five-day validation cycle.

- [ ] **Step 4: Mark the cycle as tooling-ready but validation-in-progress**

  Update the progress record without marking Daily Brief Quality Validation complete. Link the design, plan, runbook, migration, dashboard, and report command, and leave the five-date evidence fields empty until real dates exist.

- [ ] **Step 5: Run the documentation test**

  Run: `uv run pytest tests/docs/test_brief_quality_runbook.py -q`

  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add docs/it-intelligence/daily-brief-quality-validation.md docs/it-intelligence/implementation-progress.md tests/docs/test_brief_quality_runbook.py
  git commit -m "docs: add daily brief quality dogfood runbook"
  ```

### Task 11: Full verification, independent review, and branch handoff

**Files:**

- Review: all files changed since `bc11c20`
- Modify only if verification or review identifies a concrete defect.

- [ ] **Step 1: Run focused quality-validation suite**

  Run:

  ```bash
  uv run pytest tests/models/test_brief_quality_schema.py tests/services/test_brief_quality_review.py tests/api/test_brief_quality.py tests/api/test_brief_quality_timer.py tests/evaluation/test_brief_quality_database.py tests/evaluation/test_brief_quality_metrics.py tests/evaluation/test_brief_quality_reports.py tests/scripts/test_evaluate_brief_quality_cli.py tests/docs/test_brief_quality_runbook.py -q
  ```

  Expected: PASS.

- [ ] **Step 2: Run PostgreSQL migration/integrity suite**

  With `TEST_MIGRATION_DATABASE_URL` pointing at a disposable real PostgreSQL database:

  ```bash
  uv run pytest tests/integration/test_migration_0012.py tests/integration/test_brief_quality_postgres.py -q
  ```

  Expected: PASS. Do not substitute SQLite for this claim.

- [ ] **Step 3: Run full backend and lint regression**

  Run:

  ```bash
  uv run pytest -q
  uv run ruff check .
  ```

  Expected: all tests pass; only explicitly environment-gated tests may skip.

- [ ] **Step 4: Run unchanged frontend regression**

  From `frontend/`, run the repository scripts for tests, lint, typecheck, and production build defined in `frontend/package.json`.

  Expected: PASS.

- [ ] **Step 5: Inspect the final diff and prohibited-scope search**

  Run:

  ```bash
  git diff --check bc11c20..HEAD
  git diff --stat bc11c20..HEAD
  git status --short
  ```

  Inspect every changed file for silent mutation paths, review-to-ranking imports, missing security checks, unintended public APIs, and accidental new-source functionality.

- [ ] **Step 6: Request independent HIGH-risk review**

  Ask the Reviewer to examine migration reversibility, transactional integrity, concurrency, access control, latest-published eligibility, deterministic reporting, and test gaps. Address only verified findings and rerun affected tests.

- [ ] **Step 7: Record verification evidence**

  Add the exact test counts, PostgreSQL environment/result, and frontend results to `docs/it-intelligence/implementation-progress.md`. Keep the operational cycle `IN_PROGRESS` until five genuine eligible dates and a generated `VALIDATION_SAMPLE_COMPLETE` report exist.

- [ ] **Step 8: Commit any verification fixes or evidence**

  ```bash
  git add <only verified fix/evidence files>
  git commit -m "chore: verify brief quality validation tooling"
  ```

  Skip this commit if verification creates no changes.

## Observable Completion Criteria

- Revision `0012` applies fresh and from `0011`, backfills pipeline provenance, and round-trips on PostgreSQL.
- A reviewer can consume `/today`, start an internal session, record every categorical judgment and structured defect, confirm omissions, accumulate bounded active review time, complete/lock, and explicitly reopen with an audit reason.
- A completed session cannot be silently mutated through service, HTTP, or concurrent writes.
- The report always evaluates the latest `PUBLISHED` version, records `LATEST_PUBLISHED_VERSION_UNREVIEWED` rather than falling back, and includes low-signal operational dates outside the quality denominator.
- Canonical JSON and derived Markdown expose all approved metrics/provenance and use `VALIDATION_SAMPLE_COMPLETE` solely as a sample-size state.
- Full backend, PostgreSQL integration, security, lint, and frontend regressions pass.
- The tooling is ready for real daily use, while the quality-validation cycle remains `IN_PROGRESS` until at least five real eligible dates are reviewed.
