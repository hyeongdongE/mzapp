# Data PoC status

## User MVP extension (2026-09-21)

The consumer architecture is implemented as a same-origin React/TypeScript/Vite PWA with anonymous
sessions, interest onboarding, personal feed/detail, lifecycle copy, evidence attribution,
feedback, saves, notification preference, behavior events, and protected product analytics.

Every production category remains `DISABLED`. LIVE publication defaults to
`MANUAL_APPROVAL_REQUIRED` and fails closed unless the successful LIVE run, publishable claim,
category availability, human approval, and suppression gates all pass. Explicit DEMO fixtures cover
ENTERTAINMENT, AI_TECH, FOOD, and GAME for UX validation without entering LIVE KPIs, evaluation,
replay, or backtest. Real LLM, Meta, and push delivery remain disabled.

This is architecture/flow readiness, not evidence that real user testing should start. The next
step is 14 days of LIVE collection and category evaluation; only evidence-qualified categories may
move to `EXPERIMENTAL`, preferably at least two before personalization validation.

Fresh MVP verification on 2026-09-21:

- Python: `228 passed, 14 skipped`; Ruff passed.
- Frontend: `6 passed`; TypeScript check and production Vite build passed.
- Native browser smoke: DEMO onboarding with three interests, personalized feed, and evidence detail
  passed with no browser console warnings or errors.
- PostgreSQL integration and Docker image build were not rerun in this session because the local
  Docker daemon and port 5432 were unavailable. The PostgreSQL-only tests therefore account for the
  14 explicit skips; no pass is claimed for unavailable infrastructure. A dedicated `0009`
  upgrade/downgrade/seed integration test is present and remains among those skips.

Independent MVP review initially found four High issues: scheduled projection was not wired,
category changes could leave stale card categories, feed claim/provenance checks were incomplete,
and review agreement metrics were not card-stable. All four were fixed with regression tests before
final re-review. Remaining concurrency/upsert work is production hardening, not a reason to weaken
the current fail-closed feed.

## Implemented

- Official Google Trends RSS and Wikimedia Analytics collection with raw byte retention, per-fetch
  provenance, source/acquisition timestamps, retries, redacted failures, and idempotency.
- Deterministic source-scoped candidates, conservative Wikidata entity resolution, alias trust,
  ambiguity fallback, category classification, and immutable resolution/classification history.
- Explainable baseline/noise-aware scoring and `NEW`, `RISING`, `HOT`, `COOLING` lifecycle with
  cutoff-safe source/acquisition queries and internal-relative-score labeling.
- Evidence-only summaries, typed provenance validation, contradiction checks, unsupported claim
  blocking, exact claim/evidence/snapshot links, cache, and disabled LLM/Meta providers.
- Local internal dashboard, six audited review actions, human-evaluation labels, daily/weekly metric
  reports, replay digest/run identity, and a single-process scheduler.
- Docker/Native runbook, security/data-source/evaluation/replay documentation, unit/fixture/PostgreSQL
  integration tests, and actual official-source/DB smoke results.

## Not implemented

- Login/user profiles, recommendation ML, payments, social/community, native apps, actual push
  delivery, or production public deployment. These are explicit non-goals.
- Real LLM generation and live Instagram/Threads calls. They are not needed for the PoC.
- Automatic promotion to `READY_FOR_USER_MVP`; product thresholds have not been agreed and only one
  complete official-source day exists.

## Blocked

- Meta validation remains `DISABLED` until official API permission, App Review, use-case approval,
  credentials, and rate limits are confirmed. It does not block the official-source pipeline.
- No additional source is marked `BLOCKED_SOURCE`; unapproved sources remain forbidden rather than
  being probed or integrated.

## Deferred

- The documented nondeterministic external-summary concurrency reservation must be added before any
  real LLM provider is enabled. It does not affect the deterministic evidence-only provider.
- Multi-node scheduler locking, public dashboard auth UX, high-volume query optimization, and
  production observability are deferred because they are outside this PoC.
- Candidate-level Wikidata retry cooldown and automatic API/compute/human-time cost instrumentation
  remain operational follow-ups; missing cost data is explicitly reported as `N/A`.
- A 14–28 day collection period and human review sample are operational follow-up, not work that can
  be completed inside this implementation session.

## Architecture

```text
Official Google RSS / Wikimedia API
                 │
                 ▼
collection_runs ─ raw_fetches ─ raw_payloads
                 │
                 ▼
source_observations → candidates → historical entity attempts
                                      │
                                      ▼
                         classification → score/lifecycle snapshots
                                                 │
                                                 ▼
                              evidence → claims → dashboard review
                                                 │
                                                 ▼
                              daily facts → weekly report / replay digest
```

One Python modular monolith owns these stages. PostgreSQL is the only stateful service; no Kafka,
Redis, search cluster, microservice split, CQRS, or production-only infrastructure was added.

## Completion criteria mapping

| # | Criterion | Evidence |
|---:|---|---|
| 1 | Google official collection | `GoogleTrendsRssCollector`, live runs and collector tests |
| 2 | Wikimedia collection | `WikimediaTopPagesCollector`, live runs and collector tests |
| 3 | Raw data stored | `raw_payloads`/`raw_fetches`, hash replay checks |
| 4 | Repeated observations accumulate | Per-run `source_observations`, idempotency/concurrency tests |
| 5 | Trend candidates | `CandidateGenerator` and candidate tests |
| 6 | Entity candidate merge | Resolver links plus audited dashboard MERGE/SPLIT |
| 7 | Wikidata normalization | Official read-only client, historical raw/attempt provenance |
| 8 | Category classification | Versioned metadata/rule classifier and OTHER fallback |
| 9 | Four lifecycle states | Lifecycle/detection tests for NEW/RISING/HOT/COOLING |
| 10 | Score breakdown | Persisted components/weights/contributions and dashboard display |
| 11 | Noise/baseline suppression | Structural, baseline, repetition, news-only penalties/tests |
| 12 | Evidence/Claim linkage | `claim_evidence` and `claim_snapshots` FK-backed links |
| 13 | Unsupported AI blocked | Evidence checker, legacy quarantine, publication flag tests |
| 14 | Internal review dashboard | Today/List/Detail and six transactional review actions |
| 15 | Daily evaluation report | `scripts/evaluate.py daily`, real 2026-09-20 output |
| 16 | Category coverage | All enum categories emitted, including zero rows |
| 17 | Raw replay | Raw decode/reparse, historical projection, six-hour history, version/hash digest tests |
| 18 | Future Meta interface | `TrendValidationProvider` and named disabled providers |
| 19 | Works without Meta | Full test/pipeline paths use disabled providers |
| 20 | Tests pass | 167 local tests plus PostgreSQL/migration integrations; fresh evidence in `docs/poc-plan.md` |
| 21 | README local run | Exact Docker and native PowerShell commands in `README.md` |

## Current evaluation

The evaluation contract now uses an acquisition-day cohort for raw observations and unique resolved
entities; source-day candidates are reported separately as a diagnostic and the scheduler refreshes
D-2 after delayed Wikimedia arrives. Category rows include raw supply, unique entities, valid and
usable cards, and quality rates. Missing cost capture is rendered `N/A`, never a misleading zero.
Historical reports reconstruct resolution plus MERGE/SPLIT state at the report cutoff.

## Known risks

- Official RSS plus Wikimedia may remain sparse for FOOD, MEME_INTERNET, FASHION_BEAUTY, and
  SHOPPING_PRODUCT after sufficient collection.
- Google RSS news/sports spikes and Wikimedia structural popularity require continued human review;
  rule penalties reduce but cannot perfectly identify cultural trend value.
- Wikidata ambiguity is intentionally under-merged, increasing manual review and reducing supply.
- One complete day cannot establish stable precision, usable-card rate, latency, or cost per card.

## Next decision

`CONTINUE_DATA_COLLECTION`

Reason: implementation and replayability are available, but there are not yet 14 complete days or a
non-zero reviewed-card denominator. `READY_FOR_USER_MVP`, category reduction, new-source work, and
non-viability would all be premature without that evidence.
