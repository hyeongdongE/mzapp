# Replay and operations

## User MVP publication operations

All real categories are seeded `DISABLED`. Operators change `category_settings` only after reviewing
category-level valid trends/day, usable-card rate, noise rate, discovery value rate, and
already-known rate at `/internal/category-performance`. Personalization validation should wait for
at least two categories at `EXPERIMENTAL` or `ENABLED`.

```powershell
uv run python scripts/category_status.py list
uv run python scripts/category_status.py set AI_TECH EXPERIMENTAL `
  --actor operator-id --reason "14-day category evaluation passed"
```

Production uses `PUBLICATION_POLICY_MODE=MANUAL_APPROVAL_REQUIRED`. A LIVE card additionally needs a
successful LIVE run, snapshot-linked publishable claims, an enabled/experimental category, current
human `APPROVED` state, and no suppression. `AUTO_PUBLISH_ELIGIBLE` is a shadow mode: it measures
automatic eligibility but preserves manual publication. `AUTO_PUBLISH` removes that manual gate;
do not enable it until false positives, unsupported claims, review rejection, usable-card rate, and
incorrect-user-feedback are stable.

The scheduled LIVE pipeline projects cards after the pipeline run is marked successful in the same
transaction. Public eligibility rechecks that the card, entity, snapshot, and run agree and that
both publishable `WHAT` and `INTEREST` claims are linked to that exact snapshot. A projection error
marks the run failed; it cannot leave a card from a failed or replay run publicly eligible.

Demo fixtures are opt-in and bounded:

```powershell
$env:DEMO_MODE_ENABLED='true'
uv run python scripts/demo_data.py seed
uv run python scripts/demo_data.py clean
uv run python scripts/demo_data.py clean --execute
```

The preview reports the exact DEMO card count. Cleanup removes only DEMO cards and their isolated
users/interactions/events. It never changes LIVE pipeline or evaluation rows.

## Replay semantics

`scripts/replay.py` accepts an inclusive ISO date range. Date-only `--from` maps to UTC day start;
date-only `--to` maps to UTC day end. Datetimes must include a timezone and are normalized to UTC.

Replay never calls Wikidata or any other external source. It verifies and decodes immutable
`raw_payloads`, selects the parser recorded by each `raw_fetch`, parses the official Google/Wikimedia
bytes again, and normalizes the parsed item text. Candidate-to-entity links come from the latest
successful **LIVE** `EntityResolutionAttempt` known at each cutoff, never the mutable current link.
Future payloads and future resolution decisions therefore cannot alter a historical digest.
Raw input starts 32 days before `--from` to warm the scorer baseline, while derived snapshots still
start at `--from`. Warm-up fetches and their URL/timestamps are included in the digest provenance.

```powershell
uv run python scripts/replay.py `
  --from 2026-09-18 `
  --to 2026-09-20 `
  --normalizer-version normalizer-v1 `
  --entity-version entity-v1 `
  --classifier-version classifier-v2 `
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
snapshots and run order. Normalizer/entity/classifier/prompt replay versions are currently restricted
to the implemented `*-v1` values; unsupported labels fail instead of misrepresenting the code used.
A new scoring algorithm must use a new `score_version`.

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
`score-replay-warmup-v3`:

```text
dry-run snapshots=2 digest=f118099aaa0d3df45365165299dffa8d99cfd718ae19612abb0492c1e7ef2de2
run_id=19 snapshots=2 digest=f118099aaa0d3df45365165299dffa8d99cfd718ae19612abb0492c1e7ef2de2
```

PostgreSQL stored run 19 as `REPLAY / SUCCEEDED`. Its two snapshots are ordered at 18:00 and 00:00
UTC and both are `NEW` with the same explainable score; dry-run and persisted digests matched.
