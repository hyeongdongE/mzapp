# SoloPilot First Vertical Slice Implementation Progress

Canonical base: `a229c14`  
Branch: `codex/solopilot-it-intelligence-v0`

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
- Live GET validation: all five source families and both configured GitHub repositories completed against an in-memory database; the already-closed window correctly published a zero-item `LOW_SIGNAL_DAY` rather than padding a brief.
- Backend, frontend, typecheck, lint, and build commands are recorded in `quality-evaluation.md` and the task ledger.
- Durable live validation against the configured PostgreSQL URL remains incomplete because that database did not accept a connection. The in-memory live run is recorded separately and is not represented as a durable deployment check.

## Explicitly out of scope

Long-term trend inference, personalization, X, arXiv, Hugging Face, Ask SoloPilot, Brief Item saving, and a large internal package/repository rename remain unstarted.
