# First Vertical Slice Quality Evaluation

Evaluation date: 2026-09-23
Code baseline: `a229c14`
Recorded-payload E2E command: `.venv/Scripts/python.exe -m pytest tests/e2e/test_intelligence_vertical_slice.py -q`

## Golden Dataset

The checked-in dataset contains 50 deterministic RawItems. It includes a four-source same-event positive fixture and hard negatives for same entity/different event, same-day/different release, follow-up versus new event, identical titles for unrelated products, and product-name collisions. Tests enforce each declared cluster count. A follow-up without an explicit incident identity remains separate rather than risking an incorrect merge.

| Metric | Observed result | Denominator / definition |
| --- | ---: | --- |
| Golden Dataset size | 50 | RawItems |
| Incorrect Merge | 0 (0%) | 25 items across five hard-negative groups |
| Expected exact duplicates | 12 | duplicate items after each group anchor |
| Duplicate Escape | 0 (0%) | 0 missed out of 12 expected exact duplicates |
| Unclustered | 0 (0%) | all 50 Golden items received a NEW, REVIEW, or MERGE cluster assignment |

The gate is asymmetric: a known incorrect merge fails the slice; a duplicate escape is lower severity but is still measured.

## Recorded HTTP-payload vertical slice

Checked-in HTTP payload fixtures are passed through the production collectors and persistence/services; the test does not use an alternate fixture-only pipeline. These fixtures verify parsing and the end-to-end contract deterministically, but they are not reported as a successful live-provider run.

| Metric | Observed result |
| --- | ---: |
| Enabled source coverage | 5/5 |
| RawFetch rows | 5 |
| RawItem rows | 7 |
| EventCluster rows | 6 |
| EventFact rows | 22 |
| EventAssessment rows | 6 |
| Selected Brief Items | 3 |
| Brief FACT/evidence snapshots | 14 |
| Unsupported claims | 0/14 (0%) |
| Duplicate event cards | 0 |
| Final reading time | 52 seconds |
| Publication status | `PUBLISHED` |

The 52-second result is below the five-minute hard gate; the gate is a maximum, not a requirement to add filler. Every selected item has source links and exact `BriefItemFact(event_fact_id, event_evidence_id)` snapshots.

## PostgreSQL production persistence validation

An isolated PostgreSQL 16.15 container and named volume were used so the existing development database and volume were not modified. Both schema entry paths passed:

- fresh Alembic apply from an empty database: `0001 → 0011`;
- existing Trend Radar schema at `0010 → 0011`, with a pre-upgrade anonymous-user marker preserved and the new intelligence tables present.

The production collectors and services then fetched live providers and persisted the results to PostgreSQL. A validation clock immediately after the next publication cutoff was injected for the final coverage-gate pass; source content and parsing remained live.

| PostgreSQL/live metric | Observed result |
| --- | ---: |
| Initial enabled-source collection | 6 successful collector instances |
| Initial RawItems | 121 |
| Final RawItems after cutoff validation poll | 122 |
| EventClusters | 118 |
| EventFacts | 362 |
| EventEvidence | 121 |
| EventFactEvidence links | 367 |
| Persisted DailyBrief status | `PUBLISHED` |
| Persisted BriefItems | 3 |
| BriefItemFact provenance links | 11 |
| Final reading time | 60 seconds |
| `/today` after PostgreSQL restart | `PUBLISHED`, 3 items, brief date `2026-09-23` |

The first exact-run replay exposed a real idempotency defect: the service fetched a mutable live payload before noticing that the run key had already succeeded. A regression test was written first, then the intelligence collection boundary was changed to return the immutable stored run/fetch result without refetching. Replaying the original six collector run keys then preserved exactly 6 collection runs, 6 raw fetches, 6 raw payloads, and 121 RawItems while reporting zero new items.

The PostgreSQL container was restarted after publication. A new application process and session returned the same three-item published brief from `/today`, and all persisted counts remained unchanged.

## Final local verification

- Ruff: all checks passed.
- Backend with PostgreSQL: 354 non-migration tests passed, including all opt-in PostgreSQL integration tests.
- Alembic migration regression: five migration test files passed independently against fresh PostgreSQL databases (359 total backend tests across isolated database lifecycles).
- Frontend: 3 files / 16 tests passed.
- TypeScript typecheck: passed.
- ESLint: passed.
- Vite production build: passed.
