# Replay and operations

## Replay semantics

`scripts/replay.py` accepts an inclusive ISO date range. Date-only `--from` maps to UTC day start;
date-only `--to` maps to UTC day end. Datetimes must include a timezone and are normalized to UTC.

Replay never calls Wikidata or any other external source. It verifies and decodes immutable
`raw_payloads`, selects the parser recorded by each `raw_fetch`, parses the official Google/Wikimedia
bytes again, and normalizes the parsed item text. Candidate-to-entity links come from the latest
successful **LIVE** `EntityResolutionAttempt` known at each cutoff, never the mutable current link.
Future payloads and future resolution decisions therefore cannot alter a historical digest.

```powershell
uv run python scripts/replay.py `
  --from 2026-09-18 `
  --to 2026-09-20 `
  --normalizer-version normalizer-v1 `
  --entity-version entity-v1 `
  --classifier-version classifier-v1 `
  --score-version score-v2 `
  --prompt-version prompt-v1 `
  --dry-run
```

Dry-run writes nothing. Persisted replay creates an isolated `pipeline_runs(kind=REPLAY)` row,
versioned snapshots, and a canonical SHA-256 digest over the full version set, raw hashes/parser
provenance, and derived snapshots. If a live/replay snapshot already owns
the same entity/cutoff/score-version key, persistence fails and requires a new score version instead
of silently attaching another run to that row. Review and human-evaluation records are never changed.

The replay advances in six-hour cutoffs and uses only snapshots created earlier in that same replay
run for lifecycle state. This makes HOT/COOLING history independent of pre-existing database
snapshots and run order. A new algorithm must use a new `score_version`.

## Scheduler

The single-process APScheduler uses stable IDs, `replace_existing`, `coalesce=True`, and
`max_instances=1`:

| Job | Asia/Seoul schedule |
|---|---|
| Google Trends collection | Every hour |
| Wikimedia collection | Daily 09:05, targeting the date two days earlier |
| Entity/classification/scoring/summary pipeline | Hourly at minute 10 |
| Daily evaluation | Daily 09:30 for the previous UTC day, plus D-2 refresh after delayed Wikimedia |
| Weekly evaluation | Monday 10:00 |

Each source is a separate job, so a Google failure does not suppress Wikimedia or reporting.
APScheduler records exceptions in logs and continues later jobs. SIGINT/SIGTERM performs a waiting
shutdown so an active database transaction can finish.

```powershell
docker compose up -d scheduler
docker compose logs -f scheduler
```

The scheduler intentionally has no distributed lock or multi-node deployment. Run one scheduler
process for this PoC.

## Observed replay smoke (2026-09-21)

Range `2026-09-18T00:00Z` through `2026-09-21T00:00Z`, version
`score-replay-raw-v2`:

```text
dry-run snapshots=2 digest=09462f0839929735fdee3943c7f91150705425899431c60808fc01fdd832bf13
run_id=17 snapshots=2 digest=09462f0839929735fdee3943c7f91150705425899431c60808fc01fdd832bf13
```

PostgreSQL stored run 17 as `REPLAY / SUCCEEDED`. Its two snapshots are ordered at 18:00 and 00:00
UTC and both are `NEW` with the same explainable score; dry-run and persisted digests matched.
