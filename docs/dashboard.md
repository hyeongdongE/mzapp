# Internal review dashboard

The dashboard is a server-rendered FastAPI/Jinja tool for PoC review, not a consumer UI.

## Run locally

```powershell
docker compose up -d --build api
```

Open `http://127.0.0.1:8000/internal`. Compose publishes port 8000 on host loopback only. The
application also defaults to local-only access, so browser navigation and form submissions do not
need credentials in this mode.

For any non-loopback `DASHBOARD_HOST`, both of the following are mandatory:

```text
DASHBOARD_ALLOW_PUBLIC=true
DASHBOARD_API_KEY=<non-empty secret supplied outside the repository>
```

Public-mode requests must provide the secret in `X-API-Key`. The key is represented as a Pydantic
secret and is not emitted by settings representation. Do not commit a real key. The health endpoint
remains unauthenticated and only returns `{"status":"ok"}`.

## Screens

- **Today**: UTC-day raw candidate and newly created entity counts plus distinct entities approved
  or rejected/noise-reviewed that day. Use `/?date=YYYY-MM-DD` for a replay date.
- **Candidate List**: entity name, category, latest lifecycle and internal relative score, first
  candidate observation time, official sources, evidence count, and review status.
- **Detail**: aliases, Wikidata match, linked raw observations and source/acquisition timestamps,
  score history and breakdown, evidence-grounded claims, evidence URLs, and linked candidate IDs.
- **Users** (`/internal/users`): LIVE-only anonymous user and D1/D7 return counts.
- **MVP metrics** (`/internal/mvp-metrics`): impressions, opens, feedback, saves, discovery value,
  already-known, interest-failure, incorrect, open, save, and return rates.
- **Category performance** (`/internal/category-performance`): the evidence inputs used for manual
  category-state decisions plus automatic-pipeline versus human-approval agreement.

The displayed score is explicitly labeled as an internal relative score, not a probability.
External evidence is rendered as escaped data. The server does not fetch URLs embedded in titles,
metrics, claims, aliases, or review input.

## Review and evaluation writes

Supported review actions are `APPROVE`, `REJECT`, `MERGE`, `SPLIT`, `CHANGE_CATEGORY`, and
`MARK_NOISE`. Each write:

1. locks and reloads the entity,
2. checks the submitted entity version,
3. applies the mutation and appends a `reviews` audit row in one transaction,
4. rejects stale writes with HTTP 409 and invalid requests with HTTP 422.

Each applicable review also freezes its LIVE product-card ID, snapshot ID, category at review,
automatic pipeline result, and human override reason. `CHANGE_CATEGORY` updates existing LIVE
projections in the same transaction so an old enabled category cannot remain publicly visible.

`MERGE` transfers all candidate links and non-duplicate aliases to the selected target. `SPLIT`
transfers only the explicitly submitted candidate IDs, all of which must belong to the source.
Human evaluation labels are appended independently to `human_evaluations`.

## Phase verification (2026-09-21)

- Dashboard/API/security focused suite: 13 passed.
- PostgreSQL review integration: 1 passed; the transaction was rolled back after assertions.
- Rebuilt Compose image served `/healthz`, `/`, `/candidates`, `/entities/1`, and
  `/static/styles.css` successfully.
- Live DB inspection at Alembic `0008` showed 33 candidates, one entity, zero reviews, and zero
  human evaluations before and after the rollback-only integration check.
- LLM and Meta provider flags remain disabled.
