# GeekNews Minimal Integration and Mini PC Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the official GeekNews Atom feed to the existing LIVE pipeline and produce a secure, minimal mini-PC Docker deployment.

**Architecture:** Reuse `CollectionBatch`, `SourceObservation`, candidate generation, Wikidata resolution, scoring, evidence, review, and feed projection. Add one deterministic Atom parser and extend existing source dispatch points; deployment uses the existing application image behind Caddy with private PostgreSQL.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL 16, defusedxml, APScheduler, React/Vite, Docker Compose, Caddy 2.

**Spec:** `docs/superpowers/specs/2026-09-21-geeknews-mini-pc-deploy-design.md`

## Global Constraints

- Official GeekNews RSS only; no HTML, comments, users, private endpoints, or browser automation.
- No scoring threshold, taxonomy, publishable claim, manual review, or LIVE/DEMO gate changes.
- No LLM, Meta, push, new infrastructure service, or automatic approval.
- Production uses `DEMO_MODE_ENABLED=false`, `MANUAL_APPROVAL_REQUIRED`, private PostgreSQL, HTTPS, restricted internal routes, and externalized secrets.
- Scheduler interval for GeekNews is one hour and uses the existing overlap guard.

## Review Focus

- Atom entries with missing or ambiguous identity must fail closed rather than produce unstable duplicates.
- Entry links outside `news.hada.io` must not become trusted GeekNews provenance.
- Repeated collection and replay must not multiply observations or change raw provenance.
- GeekNews-only observations must not receive invented popularity strength or bypass classification/review gates.
- Production configuration must not expose PostgreSQL or the internal dashboard publicly.

---

### Task 1: GeekNews collector and collection CLI

**Files:**
- Create: `app/collectors/geeknews.py`
- Create: `tests/fixtures/geeknews_atom.xml`
- Create: `tests/collectors/test_geeknews.py`
- Modify: `app/models/enums.py`
- Modify: `app/config/settings.py`
- Modify: `scripts/collect.py`
- Modify: `tests/scripts/test_collect_cli.py`

**Interfaces:**
- Produces: `parse_geeknews_atom(raw_bytes, observed_at, fallback_url) -> list[SourceItem]` and `GeekNewsAtomCollector.collect(as_of) -> CollectionBatch`.

- [ ] Add failing parser/collector/CLI tests covering normal, empty, malformed, timeout, timestamp, safe link, and deterministic ID behavior.
- [ ] Run targeted tests and confirm failures are caused by the missing source/parser.
- [ ] Implement the minimal source enum, validated setting, collector, host allowlist, and CLI choice.
- [ ] Run targeted collector, collection-service, settings, outbound-security, and CLI tests.
- [ ] Commit `feat: add GeekNews RSS trend source`.

### Task 2: Pipeline, evidence, replay, dashboard, and scheduler wiring

**Files:**
- Modify: `app/ai/contracts.py`
- Modify: `app/ai/evidence.py`
- Modify: `app/pipeline/detection.py`
- Modify: `app/services/replay.py`
- Modify: `app/evaluation/database.py`
- Modify: `app/evaluation/metrics.py`
- Modify: `app/api/dashboard.py`
- Modify: `app/services/scheduler.py`
- Modify: `scripts/scheduler.py`
- Modify: corresponding focused tests under `tests/ai`, `tests/pipeline`, `tests/services`, and `tests/evaluation`

**Interfaces:**
- Consumes: Task 1 `Source.GEEKNEWS` and `parse_geeknews_atom`.
- Produces: replayable, approved GeekNews trend evidence and an hourly scheduled collection action.

- [ ] Add failing tests for approved provenance, interest copy, replay parsing, zero invented strength, discovery metrics, dashboard label, and hourly scheduler wiring.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Add exact-source dispatch only; keep metric/rank absent and reuse all existing gates.
- [ ] Run focused pipeline/evidence/replay/evaluation/scheduler tests.
- [ ] Commit `feat: connect GeekNews to live pipeline`.

### Task 3: Actual PostgreSQL LIVE verification

**Files:**
- Modify: `docs/data-sources.md`
- Modify: `docs/operations.md`

**Interfaces:**
- Consumes: Tasks 1-2 source pipeline.
- Produces: measured RSS, candidate, entity, category, publishable, approved, and feed counts.

- [ ] Back up or record the current database, migrate to head, and collect Google, Wikimedia, and GeekNews once with LIVE settings.
- [ ] Run the existing pipeline and inspect raw provenance, candidates, resolution, classification, snapshots, claims, and cards.
- [ ] Approve at most one genuinely useful GeekNews-derived candidate; never force a category or lower a gate.
- [ ] Smoke-test feed/detail/save/feedback only if a GeekNews-derived eligible card exists; otherwise report the exact blocker.
- [ ] Document the source and operational commands.
- [ ] Commit `test: verify GeekNews live pipeline`.

### Task 4: Mini PC production deployment

**Files:**
- Create: `compose.prod.yaml`
- Create: `deploy/Caddyfile`
- Create: `scripts/backup-db.sh`
- Create: `.env.production.example`
- Create: `docs/mini-pc-deployment.md`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Produces: `docker compose --env-file .env.production -f compose.prod.yaml ...` deployment commands.

- [ ] Add executable/config validation tests or commands for backup behavior, Compose interpolation, secret separation, private DB networking, internal route blocking, health checks, and restart policies.
- [ ] Implement the minimal production Compose, Caddy routing, backup script, environment example, and copy-paste operations documentation.
- [ ] Validate Compose config, build images, migrate fresh and existing databases, restart persistent storage, and smoke-test health and route boundaries locally.
- [ ] Run frontend tests/typecheck/lint/build once.
- [ ] Commit `chore: add mini PC production deployment` and `docs: document self-hosted operations` as coherent changes.

### Task 5: Final verification and independent review

**Files:**
- Review all branch changes; modify only for Critical/High findings.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified release readiness or precise `USER_ACTION_REQUIRED` items.

- [ ] Run backend full tests, Ruff, frontend verification, Compose config/build, migration, health, LIVE/DEMO checks, and `git diff --check`.
- [ ] Run one independent review focused on official-source compliance, provenance, LIVE gate, DB/admin exposure, CORS/same-origin, DEMO leakage, and secrets.
- [ ] Fix Critical/High findings with RED-to-GREEN tests, then rerun proportional verification once.
- [ ] Report actual GeekNews supply, LIVE cards, deployment state, security, scheduler, cost, and any mini-PC/DNS action required.
