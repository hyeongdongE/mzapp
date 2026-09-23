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

## Live GET-only validation

Attempted command:

```powershell
.venv/Scripts/python.exe scripts/run_intelligence_pipeline.py --collect --process --brief-date 2026-09-23 --dry-run
```

The configured-database attempt was interrupted after producing no CLI result. A timed Python stack dump located the wait in the PostgreSQL connection, after the GeekNews fetch/parser had completed; it was not an HTTP collector timeout.

The same production collectors and services were then run without durable writes against an in-memory database. The first run exposed a real `openai/codex` GitHub response above the 2 MB safety limit and correctly produced `DEGRADED_SOURCE_COVERAGE`. After bounding the 15-minute GitHub poll to the latest release, a fresh run produced:

| Live metric | Observed result |
| --- | ---: |
| GeekNews | 50 RawItems |
| Hacker News | 29 RawItems |
| GitHub Releases | 1 + 1 RawItems; both configured repositories healthy |
| Cloudflare Blog | 20 RawItems |
| AWS News Blog | 20 RawItems |
| Total RawItems | 121 |
| EventClusters | 83 |
| EventFacts | 257 |
| Closed-window publication | `LOW_SIGNAL_DAY` |
| Selected items / reading time | 0 / 0 seconds |

The zero-item result is not padded: collection occurred after the last 07:30 Seoul cutoff, and no event in that already-closed publication window met the gate. It demonstrates real provider collection, processing, coverage classification, and the low-signal publication path. A non-empty live three-to-seven-item brief cannot be claimed from this run; the deterministic recorded-payload E2E remains the evidence for the normal publication path. Durable validation against the configured PostgreSQL instance remains environment-blocked until that database accepts connections.

## Final local verification

- Ruff: all checks passed.
- Backend: 343 passed, 15 skipped in 11.64 seconds. The skips are existing opt-in/environment integration tests.
- Frontend: 3 files / 16 tests passed.
- TypeScript typecheck: passed.
- ESLint: passed.
- Vite production build: passed.
