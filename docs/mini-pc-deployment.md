# Mini PC production deployment

This runbook is for a dedicated public Caddy deployment. **Do not run its Compose start/update
commands on the AI Company Mini PC for private SoloPilot dogfood**: they start Caddy on 80/443 and
do not specify the isolated `solopilot` Compose project. The private dogfood procedure must use
explicit `db`, `migrate`, `api`, then `scheduler` services with Caddy omitted.

This is the production path for a single Linux mini PC. It builds the existing Vite frontend into
the FastAPI image, exposes only Caddy on ports 80/443, keeps PostgreSQL on the Docker network, and
binds the internal dashboard directly to host loopback. Caddy obtains and renews the HTTPS
certificate for the configured domain.

## Architecture

```text
Internet -> Caddy :80/:443 -> FastAPI + built frontend -> PostgreSQL volume
                                  ^
                                  +-- scheduler (same image, explicit profile)

Operator SSH tunnel -> 127.0.0.1:8000/internal
```

The public proxy returns 404 for `/internal`, dashboard `/static`, and API documentation routes,
including subpaths. The API's loopback port is not reachable from the network. The public UI and
API are same-origin, so no wildcard CORS configuration is needed; state-changing public requests
enforce the request origin. LIVE mode, manual approval, secure cookies, and disabled LLM/Meta
providers are fixed in the Compose file.

Uvicorn trusts forwarded scheme/host headers because Caddy terminates TLS. That trust is safe only
within this topology: the API port remains Docker-internal plus host-loopback and must never be
published on a LAN/public interface. This lets HTTPS browser origins match the reconstructed HTTPS
request URL while Caddy remains the sole network-facing entry point.

## Prerequisites

- Linux x86_64 or arm64 host supported by the selected Docker images
- Docker Engine and Docker Compose v2
- A domain A/AAAA record pointing to the mini PC public address
- Router/NAT forwarding TCP 80 and 443 to the mini PC
- Host firewall allowing 80/443 only, plus the user's existing restricted SSH policy
- At least 10 GB free disk for images, database growth, and backups

Record the actual OS, architecture, RAM, disk, Docker versions, existing services, public IP/NAT,
domain, and proxy before deployment:

```sh
uname -a
uname -m
free -h
df -h
docker version
docker compose version
sudo ss -lntp
```

## Environment

```sh
cp .env.production.example .env.production
chmod 600 .env.production
```

Edit `.env.production` with the real domain, a long random PostgreSQL password, its URL-encoded
equivalent in `DATABASE_URL`, a monitored contact address in `USER_AGENT`, and the PoC start date.
The real file and `backups/` are ignored by Git.

Validate the resolved configuration before starting it. Treat the output as sensitive because it
contains the resolved database URL.

```sh
docker compose --env-file .env.production -f compose.prod.yaml config --quiet
```

## First deploy and migration

Back up an existing installation before pulling or migrating. On the first deployment there is no
database to dump, so build and run the migration directly:

```sh
docker compose --env-file .env.production -f compose.prod.yaml build
docker compose --env-file .env.production -f compose.prod.yaml run --rm migrate
docker compose --env-file .env.production -f compose.prod.yaml up -d db api caddy
docker compose --env-file .env.production -f compose.prod.yaml ps
```

`alembic upgrade head` is the only schema deployment path. Do not apply manual SQL.

## Health and public smoke test

```sh
curl --fail --silent --show-error https://trend.example.com/healthz
curl --fail --silent --show-error https://trend.example.com/
curl --fail --silent --show-error https://trend.example.com/api/public/categories
curl --fail --silent --show-error https://trend.example.com/internal
curl --fail --silent --show-error https://trend.example.com/openapi.json
```

Replace the example hostname. The first three commands must succeed; the last two must return 404.
Create a LIVE anonymous session in the browser, select an available category, and verify Feed,
Detail, Save, Saved, and Feedback. An empty Feed is valid when no card passes the unchanged LIVE
publish gate. A DEMO banner or DEMO record is never valid in this deployment.

## Internal review dashboard

Do not expose port 8000 through the router or firewall. Use an SSH tunnel:

```sh
ssh -L 8000:127.0.0.1:8000 operator@mini-pc
```

Then open `http://127.0.0.1:8000/internal`. Caddy blocks the dashboard and its assets on the public
domain. If port 8000 is occupied locally, change the left side of the SSH mapping, not the server's
loopback-only binding.

## Backup and restore

Create a mode-0600 UTC-stamped SQL dump:

```sh
./scripts/backup-db.sh
BACKUP_DIR=/mnt/backup/trend-radar ./scripts/backup-db.sh .env.production
```

Restore only during a maintenance window, after confirming the exact backup path and taking a
second copy. This replaces objects present in the dump:

```sh
docker compose --env-file .env.production -f compose.prod.yaml stop api scheduler
docker compose --env-file .env.production -f compose.prod.yaml exec -T db \
  psql -U trend_radar -d trend_radar < backups/trend-radar-YYYYMMDDTHHMMSSZ.sql
docker compose --env-file .env.production -f compose.prod.yaml up -d api
```

Copy backups off the mini PC periodically and test restoration on an isolated Compose project.

## Scheduler

`compose.prod.yaml` explicitly selects `--mode intelligence-only`. It registers only
`intelligence-collect-15m`, `intelligence-process-15m`, `intelligence-generate-0735`, and
`intelligence-publish-0800`. The default CLI `combined` mode preserves the existing legacy
scheduler for operators who intentionally invoke it outside this production Compose service.

For a fresh private dogfood deployment, check `/healthz` (HTTP 200), PostgreSQL migration,
API health, and the manual real-source pipeline before enabling the scheduler. The SPA page
`/today` should load, but its HTTP 200 does **not** prove a Brief exists. The data endpoint
`/api/public/today` may return 404 until a Daily Brief is published; do not use its HTTP 200 as
a pre-publication gate. After publication, require `/api/public/today` HTTP 200 and a persisted
published Brief, then verify `/today` presents it.

Enable the scheduler only after manual LIVE collection/pipeline verification succeeds:

```sh
docker compose --env-file .env.production -f compose.prod.yaml --profile scheduler up -d scheduler
docker compose --env-file .env.production -f compose.prod.yaml logs -f --tail=100 scheduler
docker compose --env-file .env.production -f compose.prod.yaml stop scheduler
```

The production Asia/Seoul schedule collects and processes intelligence every 15 minutes,
generates at 07:35, and publishes at 08:00. Google Trends, Wikimedia, legacy collection/pipeline,
and daily/weekly evaluation jobs are not registered in this mode. Jobs use `max_instances=1` and
coalescing to avoid overlapping instances. Manual approval remains required.

## Operations

Start, stop, restart, inspect logs, and run a backup:

```sh
docker compose --env-file .env.production -f compose.prod.yaml up -d db api caddy
docker compose --env-file .env.production -f compose.prod.yaml stop
docker compose --env-file .env.production -f compose.prod.yaml restart api caddy
docker compose --env-file .env.production -f compose.prod.yaml logs -f --tail=200 api caddy
./scripts/backup-db.sh
```

Update with a backup-first, migration-before-replacement flow:

```sh
./scripts/backup-db.sh
git pull --ff-only
docker compose --env-file .env.production -f compose.prod.yaml build
docker compose --env-file .env.production -f compose.prod.yaml run --rm migrate
docker compose --env-file .env.production -f compose.prod.yaml --profile scheduler up -d
curl --fail --silent --show-error https://trend.example.com/healthz
```

For an application rollback, keep the database backup, check out the previously verified commit,
rebuild, and restart. Confirm migration compatibility before rolling application code back. Do not
automatically downgrade the database; restore the backup only as an explicit recovery operation.

## Security checklist

- Only Caddy publishes network-facing ports; PostgreSQL has no host port.
- FastAPI port 8000 is bound to `127.0.0.1` only for the SSH-tunneled internal dashboard.
- Caddy serves HTTPS and blocks public internal/review/static-dashboard routes.
- `.env.production` and SQL backups are not committed; file permissions are restricted.
- `.env.production`, `backups/`, and SQL dumps are excluded from the Docker build context.
- `DEMO_MODE_ENABLED=false`, `MANUAL_APPROVAL_REQUIRED`, and secure session cookies are fixed.
- LLM and Meta providers remain disabled; no credentials are needed for them.
- Docker logs rotate at 10 MB with three files per long-running service.
- Do not add wildcard CORS or publicly map database/internal ports.
