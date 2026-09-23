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

## Explicitly out of scope

Long-term trend inference, personalization, X, arXiv, Hugging Face, Ask SoloPilot, Brief Item saving, and a large internal package/repository rename remain unstarted.
