# AI Personal Trend Radar Data PoC

Official-data-only Python PoC for measuring whether Google Trends, Wikimedia, and Wikidata can
sustain useful Korean trend cards. It is a modular monolith with a small internal review dashboard;
it is not a consumer application.

Real LLM and Meta providers are disabled. No unofficial scraping, pytrends, private endpoints, or
credential-dependent calls are required.

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

Open `http://127.0.0.1:8000/` for the local-only review dashboard.

Collect and process official data:

```powershell
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
```

PostgreSQL opt-in tests require an already migrated, isolated database through
`TEST_DATABASE_URL`. Migration fixture tests use `TEST_MIGRATION_DATABASE_URL`.

## Documentation

- [Implementation plan](docs/poc-plan.md)
- [Official data sources](docs/data-sources.md)
- [Entity resolution](docs/entity-resolution.md)
- [Classification](docs/classification.md)
- [Trend scoring](docs/trend-scoring.md)
- [Evidence summaries](docs/evidence-summaries.md)
- [Dashboard](docs/dashboard.md)
- [Evaluation](docs/evaluation.md)
- [Replay and operations](docs/operations.md)
- [Security](docs/security.md)
- [Final status and criteria](docs/final-status.md)

Current evidence-based next decision: `CONTINUE_DATA_COLLECTION`. Only one complete official-source
day is available, so `READY_FOR_USER_MVP` is not supported.
