# SoloPilot First Vertical Slice Implementation Progress

Canonical base: `a229c14`
Branch: `codex/solopilot-it-intelligence-v0`
Status: **COMPLETE**
Merged by PR: `#3` into `codex/geeknews-mini-pc-deploy`
Merge commit: `f523c5c`

## Completed increments

| Commit | Outcome |
| --- | --- |
| `f91878b` | First Slice design specification |
| `6f320da` | Seven safety and provenance amendments |
| `dd14429` | TDD implementation plan |
| `30071e1` | Source policy/runtime-health split and persistence model |
| `563353a` | Five enabled collectors and provenance-linked RawItems |
| `cb6342e` | Deterministic deduplication and 50-item Golden Dataset |
| `f4a51ef` | Conservative clusters, entities, and evidence |
| `6b9bb98` | Fact-level provenance and independent confidence/importance |
| `b0b90d5` | Ranking, coverage, late-arrival, count, and 300-second gates |
| `f8219d4` | Today API, pipeline CLI, and Seoul scheduler jobs |
| `46b4a44` | SoloPilot Today UI with preserved Radar/Saved/Settings routes |

## Implemented path

`GeekNews + HN + GitHub + Cloudflare + AWS → RawFetch/RawItem → Dedup → EventCluster → Evidence/Entity → Fact provenance → Confidence/Importance → Rank → Publication Gate → Daily Brief → Today API/UI`

Google Trends and Wikimedia remain in the source registry but are disabled for this slice. Internal package, database, repository, and npm names have not been broadly renamed. `/saved` is preserved for legacy Trend cards; Brief Item saving is deferred.

## Verification state

- Golden Dataset: 50 items, zero known incorrect merges, zero duplicate escapes.
- Recorded five-source E2E: passes through the production pipeline and publishes three items in 52 seconds of estimated reading time.
- Live PostgreSQL validation: all five source families and both configured GitHub repositories persisted through the production collector/service path; 122 RawItems produced 118 clusters, 362 facts, 121 evidence rows, and a three-item `PUBLISHED` brief returned by `/today` after PostgreSQL restart.
- Exact collector replay is idempotent after a live mutable-payload regression was found and fixed with a test-first terminal-success short-circuit.
- Backend, frontend, typecheck, lint, and build commands are recorded in `quality-evaluation.md` and the task ledger.
- Fresh `0001 → 0011`, existing Trend Radar `0010 → 0011`, PostgreSQL integration, migration, persistence, restart, replay, and `/today` checks all pass in the isolated validation environment.
- Post-merge regression on `f523c5c`: backend 344 passed / 15 environment-gated skips, frontend 16 passed, Ruff and ESLint passed, and the TypeScript/Vite production build passed.

The First Vertical Slice is complete. Subsequent work is gated to Daily Brief Quality Validation; source expansion and follow-on product features remain blocked until that validation produces reviewed results.

## Daily Brief Quality Validation

Branch: `codex/daily-brief-quality-validation`

- Tooling Ready for Field Use: **READY**
- 5-day Quality Validation Complete: **IN_PROGRESS**
- Eligible real Brief dates: **0 recorded in this implementation cycle**
- Validation report: **not yet eligible for `VALIDATION_SAMPLE_COMPLETE`**

Field-use readiness evidence on 2026-09-24: 399 backend tests passed against the
configured PostgreSQL integration and migration databases; the focused quality
suite passed 70 tests; PostgreSQL `0011 → 0012 → 0011 → head` migration/backfill
and concurrent review-session/activity behavior passed; Ruff, ESLint, TypeScript,
16 frontend tests, and the production frontend build passed.

The PR review follow-up also verifies the supported combined CLI chronology where
the sole selected assessment can be timestamped after the captured Brief generation
time. Migration backfill accepts that unambiguous provenance and fails closed when
legacy data contains multiple possible assessment versions.

Implementation artifacts:

- Design: `docs/superpowers/specs/2026-09-23-daily-brief-quality-validation-design.md`
- Plan: `docs/superpowers/plans/2026-09-23-daily-brief-quality-validation.md`
- Migration: `alembic/versions/0012_daily_brief_quality_review.py`
- Internal workflow: `/internal/brief-quality`
- Report command: `scripts/evaluate_brief_quality.py`
- Operations: `docs/it-intelligence/daily-brief-quality-validation.md`

The reviewer must use `/today` first and the internal surface second. `active_review_seconds` measures internal review effort only. Review data remains analytical and has no automatic path into ranking, clustering, prompts, source policy, personalization, or ML.

## Explicitly out of scope

Long-term trend inference, personalization, X, arXiv, Hugging Face, Ask SoloPilot, Brief Item saving, and a large internal package/repository rename remain unstarted.
