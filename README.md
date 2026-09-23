# SoloPilot — Daily IT Intelligence

SoloPilot turns a bounded set of community, maintainer, and official IT sources into an evidence-grounded daily brief that stays within a five-minute reading-time gate. The existing replayable Trend Radar data path and `/saved` experience remain available while the new default user surface is `/today`.

Real LLM and Meta providers are disabled. The First Slice uses GeekNews, Hacker News, GitHub Releases, Cloudflare Blog, and AWS News Blog through official RSS/API endpoints. Google Trends and Wikimedia adapters are retained but disabled in the intelligence source registry.

## Prerequisites

- Docker Desktop with Compose
- Python 3.12+ and `uv` for native development/test commands

## Docker quick start

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d db
docker compose run --rm api uv run --no-sync alembic upgrade head
docker compose up -d api
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

Open `http://127.0.0.1:8000/` for the user PWA and `/internal` for the local-only review dashboard.
Production starts with every category `DISABLED`, so an honest empty state is expected until
evaluation evidence supports an operational status change.

Collect and process official data:

```powershell
docker compose run --rm api uv run --no-sync python scripts/run_intelligence_pipeline.py --collect --process --brief-date 2026-09-23
docker compose run --rm api uv run --no-sync python scripts/collect.py --source google
docker compose run --rm api uv run --no-sync python scripts/collect.py --source wikimedia
docker compose run --rm api uv run --no-sync python scripts/build_entities.py
docker compose run --rm api uv run --no-sync python scripts/generate_summaries.py
```

Generate evaluation and replay outputs:

```powershell
docker compose run --rm api uv run --no-sync python scripts/evaluate.py daily --date 2026-09-20
docker compose run --rm api uv run --no-sync python scripts/evaluate.py weekly --week 1 --poc-start 2026-09-20
docker compose run --rm api uv run --no-sync python scripts/replay.py --from 2026-09-18 --to 2026-09-20 --score-version score-v2 --dry-run
```

Reports persist under `reports/`. Remove `--dry-run` to store a replay `PipelineRun` and its
versioned snapshots. Use a new score version when the cutoff/version already has a live snapshot.

Start automated collection, pipeline, and reporting:

```powershell
docker compose up -d api scheduler
docker compose ps
docker compose logs -f scheduler
```

The scheduler uses `POC_START_DATE` from `.env`, runs in `Asia/Seoul`, and keeps LLM/Meta disabled.

## Native Windows development

```powershell
uv sync --frozen
docker compose up -d db
$env:DATABASE_URL='postgresql+psycopg://trend_radar:trend_radar@127.0.0.1:5432/trend_radar'
uv run alembic upgrade head
uv run python scripts/collect.py --source all
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verification:

```powershell
uv run ruff check .
uv run pytest -q
uv run pytest tests/e2e/test_intelligence_vertical_slice.py -q
Push-Location frontend
npm ci
npm test
npm run typecheck
npm run build
Pop-Location
```

For isolated UX development, set `DEMO_MODE_ENABLED=true`, migrate the database, then seed explicit
fixtures. DEMO users, cards, review state, events, and KPIs never enter LIVE evaluation or replay.

```powershell
$env:DEMO_MODE_ENABLED='true'
uv run python scripts/demo_data.py seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run python scripts/demo_data.py clean          # preview exact DEMO card count
uv run python scripts/demo_data.py clean --execute
```

PostgreSQL opt-in tests require an already migrated, isolated database through
`TEST_DATABASE_URL`. Migration fixture tests use `TEST_MIGRATION_DATABASE_URL`.

## Documentation

- [IT intelligence source policy](docs/it-intelligence/source-policy.md)
- [First Slice quality evaluation](docs/it-intelligence/quality-evaluation.md)
- [First Slice implementation progress](docs/it-intelligence/implementation-progress.md)
- [Implementation plan](docs/poc-plan.md)
- [Official data sources](docs/data-sources.md)
- [GeekNews LIVE verification](docs/geeknews-live-verification.md)
- [Entity resolution](docs/entity-resolution.md)
- [Classification](docs/classification.md)
- [Trend scoring](docs/trend-scoring.md)
- [Evidence summaries](docs/evidence-summaries.md)
- [Dashboard](docs/dashboard.md)
- [Evaluation](docs/evaluation.md)
- [Replay and operations](docs/operations.md)
- [Mini PC production deployment](docs/mini-pc-deployment.md)
- [Security](docs/security.md)
- [Final status and criteria](docs/final-status.md)

Current evidence-based next decision remains `CONTINUE_DATA_COLLECTION`. The architecture and DEMO
UX are testable, but no LIVE category is enabled and public user testing should not start until
category-level evidence supports at least `EXPERIMENTAL` status.
