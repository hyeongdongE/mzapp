# Daily Brief Quality Validation Operations

This runbook starts human dogfooding while keeping the completed IT Intelligence pipeline fixed. PostgreSQL is the source of truth for every review; JSON and Markdown reports are derived artifacts that may be regenerated at any time.

## Status model

- **Tooling Ready for Field Use** is set only after schema, dashboard, reporting, real PostgreSQL concurrency checks, and full regression pass.
- **5-day Quality Validation Complete** remains **IN_PROGRESS** until one human has completed reviews for at least five distinct real Brief dates and the derived report says `VALIDATION_SAMPLE_COMPLETE`.

The sample state is not a product-quality conclusion. Fixture dates, copied Briefs, manually changed publication states, and future-clock runs never count.

## Daily workflow

1. Use `/today` as the real SoloPilot consumption surface before opening any review tooling. Read the published Brief normally and follow its evidence links as needed.
2. Open `/internal/brief-quality`, select the same Brief date and latest version, and start or resume the internal review session.
3. Confirm collector health and publication status. A date counts only when the latest `PUBLISHED` DailyBrief version has healthy coverage and a completed review. If that version is unreviewed, the report emits `LATEST_PUBLISHED_VERSION_UNREVIEWED`; it never falls back to an older reviewed version.
4. Evaluate every BriefItem: usefulness, event selection, Fact correctness, Interpretation quality, Watch usefulness, verbosity, EvidenceSet usefulness, incorrect merge, and duplicate escape. Link duplicate targets and disputed cluster memberships structurally.
5. Record every missing important event with canonical HTTPS URL and `MissingEventDiscoverySource`, or explicitly confirm that missing events were considered and none were found.
6. Complete the session. Completion locks all judgments. To correct one, use explicit reopen with an actor and reason; the prior completion revision and timestamp remain in the audit trail.

The internal timer stores `active_review_seconds`, meaning foreground/visible review effort on the internal screen. It is not actual `/today` reading time and must not be reported as such.

## Collector and publication checks

Before reviewing, confirm the scheduled collector and pipeline run succeeded, required source health is `FRESH`, and `/api/public/today` returns the expected published Brief. Do not turn a degraded or rejected day into an eligible sample manually.

`LOW_SIGNAL_DAY` remains in the dogfood operational record so the operating period is complete, but it is excluded from the Useful Brief Rate denominator and cannot satisfy one of the five eligible dates. `DEGRADED_SOURCE_COVERAGE`, `REJECTED`, and `DRAFT` are also excluded with their actual reasons.

## Generate partial and final reports

Run this after each review, even before five dates exist:

```powershell
uv run python scripts/evaluate_brief_quality.py --reviewer owner --start-date 2026-09-24 --end-date 2026-09-30 --output-dir reports
```

The command creates matching `brief-quality-<start>-<end>.json` and `.md` files atomically. JSON is the canonical derived shape; Markdown renders the same model. Inspect included and excluded Brief IDs, all pipeline/generation/clustering/assessment versions, categorical distributions, structured defect links, omission sources, Useful Brief Rate, and active review effort.

`INSUFFICIENT_VALIDATION_DAYS` means fewer than five eligible dates. `VALIDATION_SAMPLE_COMPLETE` means only that the five-date evaluation sample exists.

## Exclusion triage

- `LATEST_PUBLISHED_VERSION_UNREVIEWED`: review that exact version; do not use its predecessor.
- `SUPERSEDED_PUBLISHED_VERSION`: provenance only; no action unless the latest version is wrong.
- `INCOMPLETE_ITEM_REVIEWS`: assess every current BriefItem.
- `MISSING_EVENTS_NOT_CONFIRMED`: explicitly complete the omission assessment.
- `ZERO_ACTIVE_REVIEW_TIME`: perform the review in a visible, focused internal review screen.
- `MISSING_VERSION_PROVENANCE`: stop and diagnose persistence/generation; never invent a version.
- publication statuses such as `LOW_SIGNAL_DAY` or `DEGRADED_SOURCE_COVERAGE`: retain them in the operational record without forcing eligibility.

## Backup and recovery

Back up PostgreSQL before maintenance using the repository backup command:

```powershell
docker compose exec -T db sh -c 'pg_dump --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' > brief-quality-backup.sql
```

Review records must survive service restart. Markdown/JSON files are not restoration inputs; regenerate them from PostgreSQL after recovery.

## Frozen-pipeline rule

This subsystem stores and analyzes human feedback only. It does not modify ranking, clustering, prompts, or source policy, and it does not train or drive personalization or ML. Do not add sources or begin X, arXiv, Hugging Face, personalization, Radar enhancement, or Ask SoloPilot work during this validation cycle.
