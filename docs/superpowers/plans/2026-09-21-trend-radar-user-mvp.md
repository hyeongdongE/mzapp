# Personal Trend Radar User MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mobile-first anonymous Personal Trend Radar PWA on the verified Data PoC without weakening its evidence or evaluation rules.

**Architecture:** Extend the FastAPI/PostgreSQL modular monolith with isolated product-card and anonymous-user tables, a policy-driven public API, protected product analytics, and a same-origin React/TypeScript/Vite PWA. LIVE cards project verified pipeline records; explicit DEMO/TEST projections exercise UX without contaminating LIVE review, KPI, evaluation, or replay data.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, pytest, React 19, TypeScript, Vite, Vitest, Testing Library, PWA manifest/service worker.

**Spec:** `docs/superpowers/specs/2026-09-21-trend-radar-user-mvp-design.md`

## Global Constraints

- Preserve existing pipeline, scoring, evidence, replay, and evaluation behavior.
- Production starts with every category `DISABLED` and publication policy `MANUAL_APPROVAL_REQUIRED`.
- Public production APIs return only `LIVE`; `DEMO`/`TEST` never enter LIVE KPIs or Data PoC evaluation.
- Real LLM, Meta, and push delivery remain disabled.
- No unsupported claims, raw payloads, internal scores, or frontend secrets are exposed.
- No registration, folders, tags, sharing, ML ranking, or production architecture expansion.

## Review Focus

- A forged or another user's identifier must never read or mutate interests, feedback, or saves.
- A DEMO/TEST record must never appear in production feed, LIVE KPI, evaluation, or replay queries.
- A LIVE card missing any run, claim, category, review, or suppression gate must remain invisible.
- Repeated feedback/save/event requests must be idempotent and keep rate denominators meaningful.
- Empty categories, no eligible cards, missing metrics, offline UI, and stale card IDs must fail safely.

---

### Task 1: Product and user schema

**Files:**
- Modify: `app/models/enums.py`
- Modify: `app/models/tables.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/0009_user_mvp.py`
- Modify: `tests/models/test_schema.py`
- Create: `tests/integration/test_migration_0009.py`

**Interfaces:**
- Produces typed enums for data mode, category state, publication policy, feedback, notification, and events.
- Produces category settings, product cards, anonymous users, interests, interactions, feedback, saves, preferences, and events.

- [ ] Write schema tests proving constraints, indexes, LIVE provenance requirements, and all-disabled seed rows.
- [ ] Run the focused model and PostgreSQL migration tests and confirm they fail for missing tables.
- [ ] Add enums, focused SQLAlchemy models, review audit columns, and migration `0009` with reversible DDL.
- [ ] Run focused tests and inspect generated PostgreSQL schema/seed rows.
- [ ] Commit the independently testable schema slice.

### Task 2: Review audit and publication policy

**Files:**
- Modify: `app/config/settings.py`
- Modify: `app/services/reviews.py`
- Create: `app/product/policy.py`
- Create: `app/product/cards.py`
- Create: `app/product/__init__.py`
- Modify: `scripts/generate_summaries.py`
- Create: `tests/product/test_policy.py`
- Create: `tests/product/test_cards.py`
- Modify: `tests/services/test_reviews.py`

**Interfaces:**
- Consumes existing `PipelineRun`, `TrendSnapshot`, `ClaimSnapshot`, `Claim`, `TrendEntity`, `Evidence`, and `Review`.
- Produces `PublicationDecision`, `PublicationPolicyEvaluator.evaluate(card, category, entity)` and `ProductCardService.sync_live(as_of)`.

- [ ] Write failing tests for every LIVE publication gate and all three policy modes.
- [ ] Write failing tests that review rows retain previous/resulting status and auto/human comparison fields.
- [ ] Implement policy configuration and a single policy evaluator; rejection/noise/suppression always deny.
- [ ] Implement idempotent LIVE projection sync from successful LIVE runs and publishable snapshot-linked claims.
- [ ] Invoke sync after deterministic summary generation without changing summary validation.
- [ ] Run focused tests plus existing summary/review/replay suites and inspect a synced card row.
- [ ] Commit the policy/projection slice.

### Task 3: Anonymous session and user preferences

**Files:**
- Create: `app/api/public.py`
- Create: `app/api/public_dependencies.py`
- Create: `app/product/users.py`
- Create: `app/product/schemas.py`
- Modify: `app/main.py`
- Create: `tests/api/test_public_session.py`
- Create: `tests/api/test_public_preferences.py`

**Interfaces:**
- Produces `POST /api/public/session`, category, interest, and settings endpoints.
- Produces `CurrentUser` dependency from a hashed opaque HttpOnly cookie.

- [ ] Write failing API tests for random credentials, hash-only storage, cookie flags, same-origin mutation checks, and missing/forged sessions.
- [ ] Write failing tests for one-interest minimum, no `OTHER`, selectable category filtering, and tenant isolation.
- [ ] Implement session creation/lookup, last-seen updates, category responses, interests, and notification preferences.
- [ ] Run focused API tests and confirm public responses contain no credential hash or internal IDs.
- [ ] Commit the anonymous-user slice.

### Task 4: Personalized feed, detail, feedback, and saves

**Files:**
- Create: `app/product/feed.py`
- Create: `app/product/ranking.py`
- Modify: `app/api/public.py`
- Create: `tests/product/test_ranking.py`
- Create: `tests/api/test_public_feed.py`
- Create: `tests/api/test_public_actions.py`

**Interfaces:**
- Consumes policy evaluator, current user, category settings, product cards, and user history.
- Produces feed/detail DTOs and feedback/save operations scoped to the current user.

- [ ] Write failing tests for category filtering, freshness/history ranking, deterministic ties, empty feed, no score leakage, and all publication gates.
- [ ] Write failing tests for impression/open aggregation, feedback upsert, save idempotency, incorrect feedback, and tenant isolation.
- [ ] Implement explainable rule-based ranking without mutating `TrendSnapshot.total_score`.
- [ ] Implement feed/detail serializers that expose supported copy and safe source attribution only.
- [ ] Implement feedback/save endpoints and interaction counters with validated mode boundaries.
- [ ] Run focused tests plus pipeline scoring/evidence regressions.
- [ ] Commit the core user-value slice.

### Task 5: Analytics and protected internal product pages

**Files:**
- Create: `app/product/analytics.py`
- Modify: `app/api/public.py`
- Modify: `app/api/dashboard.py`
- Create: `dashboard/templates/mvp_metrics.html`
- Create: `dashboard/templates/category_performance.html`
- Create: `dashboard/templates/users.html`
- Modify: `dashboard/templates/base.html`
- Create: `tests/product/test_analytics.py`
- Modify: `tests/api/test_dashboard.py`

**Interfaces:**
- Produces validated event ingestion and LIVE-only aggregate metrics.
- Produces protected `/internal/users`, `/internal/mvp-metrics`, and `/internal/category-performance`.

- [ ] Write failing tests for canonical events, invalid card references, rate denominators, D1/D7, missing denominators, and strict mode isolation.
- [ ] Implement server-owned event context and LIVE-only metrics, including auto-vs-human approval and category decision inputs.
- [ ] Move/alias existing dashboard routes beneath `/internal` and keep the access dependency on every internal page.
- [ ] Add compact operational templates with explicit LIVE/DEMO labels and unavailable-value rendering.
- [ ] Run analytics/dashboard/security tests and inspect rendered pages.
- [ ] Commit the measurement slice.

### Task 6: Demo fixtures and isolation tooling

**Files:**
- Create: `app/product/demo.py`
- Create: `scripts/demo_data.py`
- Create: `tests/product/test_demo.py`
- Create: `tests/scripts/test_demo_data_cli.py`
- Modify: `docs/operations.md`

**Interfaces:**
- Produces idempotent `seed` and bounded `clean` commands for explicit DEMO mode.

- [ ] Write failing tests for disabled-mode refusal, four-category fixture shape, idempotent seed, bounded cleanup, and zero LIVE/evaluation mutation.
- [ ] Implement DEMO fixtures for ENTERTAINMENT, AI_TECH, FOOD, and GAME with explicit labels and safe official-looking placeholder attribution.
- [ ] Implement exact-count preview and cleanup limited to `data_mode=DEMO`.
- [ ] Run fixture tests, seed twice, inspect rows, and clean them.
- [ ] Commit the demo-tooling slice.

### Task 7: React PWA shell and onboarding

**Files:**
- Create: `frontend/package.json`, `frontend/package-lock.json`, TypeScript/Vite/Vitest configuration.
- Create: `frontend/index.html`, `frontend/public/manifest.webmanifest`, `frontend/public/sw.js`.
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/types.ts`.
- Create: `frontend/src/styles.css`, `frontend/src/components/*`, `frontend/src/pages/Onboarding.tsx`.
- Create: `frontend/src/test/*` and onboarding/component tests.

**Interfaces:**
- Consumes same-origin `/api/public` JSON.
- Produces installable responsive shell, navigation, session bootstrap, onboarding, and labelled demo mode.

- [ ] Scaffold the minimal React/TypeScript/Vite app and write failing onboarding/session/accessibility tests.
- [ ] Implement design tokens, responsive shell, focus states, offline/error/loading primitives, and bottom navigation.
- [ ] Implement session bootstrap and category selection with one-item validation and three-to-five recommendation.
- [ ] Add manifest and conservative service worker that never caches personalized API responses.
- [ ] Run Vitest, typecheck, build, and inspect mobile/desktop layouts.
- [ ] Commit the PWA foundation slice.

### Task 8: Feed, detail, saved, and settings UI

**Files:**
- Create: `frontend/src/pages/Feed.tsx`, `TrendDetail.tsx`, `Saved.tsx`, `Settings.tsx`.
- Create: `frontend/src/components/TrendCard.tsx`, `LifecycleBadge.tsx`, `FeedbackBar.tsx`, `SourceList.tsx`.
- Create/modify corresponding frontend tests.

**Interfaces:**
- Consumes the public feed/detail/action/settings endpoints.
- Produces every requested end-user route and analytics call.

- [ ] Write failing route/component tests for card hierarchy, lifecycle copy, empty state, supported cause fallback, feedback, saving, and settings.
- [ ] Implement feed with intersection-based impressions and no irrelevant fallback cards.
- [ ] Implement detail with public evidence attribution and separate incorrect feedback.
- [ ] Implement saved list and interest/notification settings; do not implement push delivery.
- [ ] Verify keyboard/touch behavior, reduced motion, Korean copy, mobile/desktop views, typecheck, and production build.
- [ ] Commit the complete UX slice.

### Task 9: Same-origin delivery, documentation, and final verification

**Files:**
- Modify: `app/main.py`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `docs/security.md`, `docs/dashboard.md`, `docs/evaluation.md`, `docs/operations.md`, `docs/final-status.md`
- Create: `tests/api/test_spa.py`

**Interfaces:**
- Produces SPA history fallback without intercepting API/internal/health routes and a reproducible Docker image.

- [ ] Write failing routing tests for `/`, SPA deep links, `/api/public`, `/internal`, static assets, and missing build fallback.
- [ ] Mount built PWA assets safely and update the multi-stage Docker build.
- [ ] Document privacy, policy transitions, category gates, DEMO isolation, KPI interpretation, and disabled external providers.
- [ ] Run frontend lint/typecheck/tests/build; Ruff; full pytest; PostgreSQL migrations/integration; demo seed/clean; API health; Docker build; and diff review.
- [ ] Request independent HIGH-risk review focused on auth, tenant isolation, publication gates, mode contamination, metrics, and regressions; fix Critical/High findings and reverify.
- [ ] Commit final verified documentation/integration changes and report exact evidence.

