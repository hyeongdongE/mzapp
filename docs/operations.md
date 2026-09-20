# Replay and operations

## Replay semantics

`scripts/replay.py` accepts an inclusive ISO date range. Date-only `--from` maps to UTC day start;
date-only `--to` maps to UTC day end. Datetimes must include a timezone and are normalized to UTC.

Replay never calls Wikidata or any other external source. It reconstructs candidate-to-entity links
from the latest successful **LIVE** `EntityResolutionAttempt` at or before the cutoff and ignores the
current mutable `entity_candidates` link. Only source observations whose source and acquisition
timestamps are both within the requested range and at or before the cutoff are scored. Future
observations therefore cannot alter a historical dry-run digest.

```powershell
uv run python scripts/replay.py `
  --from 2026-09-18 `
  --to 2026-09-20 `
  --score-version score-v2 `
  --dry-run
```

Dry-run writes nothing. Persisted replay creates an isolated `pipeline_runs(kind=REPLAY)` row,
versioned snapshots, and a canonical SHA-256 snapshot digest. If a live/replay snapshot already owns
the same entity/cutoff/score-version key, persistence fails and requires a new score version instead
of silently attaching another run to that row. Review and human-evaluation records are never changed.

The replay scores the range at its final cutoff. It is a deterministic backtest building block, not
a per-hour simulation. A new algorithm must use a new `score_version`; changing only the label
without changing the checked-in algorithm does not create a different method.

## Scheduler

The single-process APScheduler uses stable IDs, `replace_existing`, `coalesce=True`, and
`max_instances=1`:

| Job | Asia/Seoul schedule |
|---|---|
| Google Trends collection | Every hour |
| Wikimedia collection | Daily 09:05, targeting the date two days earlier |
| Entity/classification/scoring/summary pipeline | Hourly at minute 10 |
| Daily evaluation | Daily 09:30 for the previous UTC day |
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

Range `2026-09-18` through `2026-09-20`, version `score-replay-smoke-v1`:

```text
dry-run snapshots=0 digest=72072fe107bfd9c4ae1dfab25d47b93bad0727fc8030da7dcb11877958bb16f2
run_id=13 snapshots=0 digest=72072fe107bfd9c4ae1dfab25d47b93bad0727fc8030da7dcb11877958bb16f2
```

The zero result is expected: the only resolved live entity was a suppressed structural Wikimedia
baseline item. PostgreSQL stored run 13 as `REPLAY / SUCCEEDED` at the exact UTC end-of-day cutoff.
