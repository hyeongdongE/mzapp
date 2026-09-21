# Personal Trend Radar User MVP Design

## Status

Approved for Native implementation on 2026-09-21. The product brief and the follow-up
publication/category decisions are authoritative. Implementation proceeds without another approval
gate unless a source is blocked or a material design change becomes unavoidable.

## Goal

Turn the verified Data PoC into a mobile-first PWA that lets an anonymous person select interests,
discover a small number of evidence-backed trends, inspect their evidence, give feedback, save
items, and return later. The MVP validates discovery value and personalization; it does not predict
future popularity or relax the Data PoC quality bar.

## Product invariants

- Accuracy and evidence take priority over card supply. An empty feed is valid.
- Existing trend detection, scoring, evidence, and claim validation remain unchanged.
- Internal trend scores are never presented as probabilities and are not returned by public APIs.
- Real LLM, Meta, and push delivery remain disabled.
- Anonymous users are identified with a random opaque credential. No fingerprinting or sensitive
  personal data is collected.
- `LIVE`, `DEMO`, and `TEST` records are separated at the product-card, review, interaction, event,
  metric, fixture, and query boundaries.
- Public production APIs accept and return only `LIVE` data. Demo mode requires an explicit
  non-production setting and a separate demo route/query context.
- `DEMO` and `TEST` records never affect Data PoC evaluation, replay/backtest, LIVE review metrics,
  or user KPIs.

## Architecture

Keep the modular FastAPI application and PostgreSQL database. Add a public API under
`/api/public`, keep protected operational pages under `/internal`, and serve a React/TypeScript/Vite
PWA from the same origin. Same-origin deployment avoids CORS credentials and keeps the anonymous
credential in an HttpOnly cookie instead of exposing it to JavaScript.

The existing pipeline remains the system of record. A small `product_trend_cards` projection gives
LIVE pipeline output and isolated DEMO/TEST fixtures one identical user-facing shape. LIVE cards
retain foreign keys to the source entity, snapshot, and successful LIVE pipeline run. A sync service
creates or refreshes LIVE projections only from snapshot-linked publishable claims. Demo fixtures
create projection rows without core-pipeline records and are explicitly marked `DEMO`.

## Data model

### Operational policy

- `category_settings`: one row per non-`OTHER` category with `DISABLED`, `EXPERIMENTAL`, or
  `ENABLED`, rationale, operator, and update timestamp. The migration seeds every category as
  `DISABLED`; no category is hardcoded active.
- `publication_policy` is a typed runtime setting with
  `MANUAL_APPROVAL_REQUIRED`, `AUTO_PUBLISH_ELIGIBLE`, and `AUTO_PUBLISH`. Production defaults to
  `MANUAL_APPROVAL_REQUIRED`.
- Existing `reviews` gain nullable audit fields for `previous_status`, `resulting_status`,
  `auto_pipeline_result`, and `human_override_reason`. Existing `actor`, `created_at`, and `reason`
  remain reviewer, reviewed-at, and review-reason.

### User-facing trend projection

`product_trend_cards` contains:

- opaque UUID public ID;
- `data_mode` (`LIVE`, `DEMO`, `TEST`);
- LIVE provenance (`entity_id`, `snapshot_id`, `pipeline_run_id`) or fixture key;
- title, category, lifecycle, supported what/interest/cause copy;
- source attribution with public URLs and observation timestamps;
- first-seen/observed timestamps;
- internal ranking component, automatic pipeline result, suppression state, and timestamps.

LIVE uniqueness is by snapshot. Fixture uniqueness is by `(data_mode, fixture_key)`. Constraints
ensure LIVE provenance is present and fixture keys are used only outside LIVE.

### Anonymous user data

- `anonymous_users`: UUID ID, SHA-256 credential hash, created/last-seen timestamps.
- `user_interests`: unique `(user_id, category)` rows.
- `notification_preferences`: one row per user; `OFF`, `DAILY_DIGEST`, or `IMPORTANT_RISING`.
- `trend_interactions`: unique `(user_id, card_id)`, first/last impression, impression/open counts.
- `trend_feedback`: unique `(user_id, card_id)` with the latest feedback and timestamps.
- `saved_trends`: unique `(user_id, card_id)` and created timestamp.
- `product_events`: validated event type, user, optional card/category, data mode, and timestamp.

All user-scoped operations derive the user from the cookie credential; they never accept a user ID
from request data.

## Publication policy

A LIVE card can be returned in production only when all base conditions hold:

1. card mode is `LIVE`;
2. referenced pipeline run is `LIVE` and `SUCCEEDED`;
3. the snapshot has at least one publishable claim, including user-facing summary copy;
4. category setting is `EXPERIMENTAL` or `ENABLED`;
5. the card is not suppressed;
6. the active publication policy permits it.

Under the initial `MANUAL_APPROVAL_REQUIRED` policy the entity must have current review status
`APPROVED`. The policy decision is isolated in one service and tested for all three enum values so
manual approval is not embedded in repository queries as a permanent requirement. Human
`REJECTED`/`NOISE` and suppression always win.

The LIVE projection records the automatic publishability result separately from the human result.
Review metrics can therefore answer: “of automatically publishable cards, what percentage did a
human approve?”

## Ranking

The pipeline `TrendSnapshot.total_score` is immutable. The product service normalizes it within the
eligible result set and computes an ephemeral feed score:

`trend component + selected-category preference + positive history + saved history - not-interested
history - already-known penalty - repeat-impression penalty + freshness`.

Only selected categories are considered. Stable constants are documented and tested; no ML is
introduced. The API returns optional plain-language ranking reasons but never numeric internal
components. Ties are deterministic by observation time and public ID.

## Public API

- `GET /api/public/categories`
- `POST /api/public/session`
- `GET|PUT /api/public/me/interests`
- `GET /api/public/feed`
- `GET /api/public/trends/{public_id}`
- `PUT /api/public/trends/{public_id}/feedback`
- `PUT|DELETE /api/public/trends/{public_id}/save`
- `GET /api/public/saved`
- `GET|PUT /api/public/settings`
- `POST /api/public/events`

Mutation endpoints enforce same-origin requests when an `Origin` header is present. Session
creation sets a `HttpOnly`, `SameSite=Lax` credential cookie; `Secure` is enabled outside explicit
local development. Unknown, disabled, wrong-mode, suppressed, or ineligible cards return 404 to
avoid leaking inventory.

## UX and information architecture

Routes are `/`, `/onboarding`, `/feed`, `/trends/:id`, `/saved`, and `/settings`. `/` sends a new
user to onboarding and a configured user to the feed. The bottom navigation contains Feed, Saved,
and Settings.

Onboarding presents enabled/experimental categories, requires at least one selection, recommends
three to five, and records the start/selection events. When production has no selectable category,
it explains that the radar is collecting evidence instead of fabricating choices. Explicit demo mode
shows fixture categories with a persistent “DEMO DATA” banner.

Feed cards use the hierarchy lifecycle, title, one-line evidence-backed summary, category/freshness,
then feedback actions. Detail shows “what”, a cause only when supported (otherwise the approved
unknown-cause copy), and source attribution. Feedback updates in place. Saved and Settings stay
minimal. Empty, loading, offline, and recoverable error states are first-class.

Visual direction uses a warm neutral surface, high-contrast ink, one restrained accent, generous
spacing, and compact cards. It avoids dashboard chrome, dense charts, gradients that imply AI, and
probability language. Touch targets are at least 44px, focus is visible, controls have accessible
names, lifecycle is conveyed by text as well as color, and motion respects reduced-motion settings.

## Analytics and category evaluation

Canonical server-side events are `ONBOARDING_STARTED`, `INTEREST_SELECTED`, `FEED_VIEWED`,
`TREND_IMPRESSION`, `TREND_OPENED`, three feedback events plus `FEEDBACK_INCORRECT`,
`TREND_SAVED`, and `RETURN_VISIT`. Duplicate impression calls within a short request window are
idempotent at the interaction level; aggregate rates use interaction counts, not raw client events.

Internal pages under `/internal` expose product users, MVP metrics, and category performance.
Default metrics include LIVE only. Demo/test views are separately labelled and cannot be combined
with LIVE. Category performance reports valid trends/day, usable-card rate, noise rate, discovery
value rate, already-known rate, automatic-publishable count, human reviewed count, approval rate,
rejection rate, unsupported claim rate, and incorrect-feedback rate. Missing denominators display
as unavailable, not zero.

## Delivery and operations

Vite emits static assets into `frontend/dist`; FastAPI serves the SPA with history fallback while
`/api/public`, `/internal`, and `/healthz` remain backend routes. The Docker build uses a Node build
stage and copies only built assets into the Python image. Development supports Vite proxying
`/api` to FastAPI.

A repeatable demo seed command inserts or updates clearly labelled DEMO fixtures in at least
ENTERTAINMENT, AI_TECH, FOOD, and GAME. It refuses to run when demo mode is disabled. A cleanup
command deletes only DEMO rows after resolving and reporting exact counts. TEST fixtures remain
transactional test data.

## Completion criteria

- Schema migration upgrades/downgrades on PostgreSQL and seeds every real category disabled.
- Public auth, tenant isolation, publication eligibility, mode isolation, ranking, feedback, saves,
  events, metrics, and review-audit behavior have automated tests.
- React flows work on mobile and desktop widths and pass component/build checks.
- DEMO data proves onboarding and personalization across at least three categories without entering
  LIVE metrics or Data PoC evaluation.
- LIVE feed is empty unless every publication condition is satisfied.
- Existing Data PoC tests, replay invariants, Ruff, frontend checks, Docker build, migration, and API
  health pass.

