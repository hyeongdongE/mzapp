# GeekNews Minimal Integration and Mini PC Deployment Design

## Goal

Add the official GeekNews Atom feed as a candidate-discovery source, verify it through the existing LIVE pipeline without weakening any publication gate, and prepare a small Linux/Docker Compose deployment for a user-owned mini PC.

## Data design

- Fetch only `https://news.hada.io/rss/news` over HTTPS.
- Parse only Atom `id`, `title`, alternate `link`, and `published`; do not persist feed content or author data.
- Store the complete response in the existing raw-payload provenance model and derive deterministic item IDs from the entry ID.
- Treat each title as a candidate input. GeekNews does not imply `AI_TECH`, popularity, `RISING`, or `HOT`.
- Add GeekNews as an approved `TREND_SIGNAL` source and replay input, while retaining the existing scoring, classification, evidence, review, and LIVE publication gates.
- Poll hourly with the scheduler's existing `max_instances=1` overlap guard.

## Deployment design

- Use one production Compose file with Caddy, the existing API image (which contains the built PWA), PostgreSQL, and the scheduler. A one-shot migration service gates API and scheduler startup.
- Publish only ports 80/443 through Caddy. PostgreSQL has no host port. The API is additionally bound to host loopback for local/SSH-tunnel access to the internal dashboard.
- Caddy blocks `/internal*` and `/static*` on the public origin. The application keeps dashboard API-key enforcement enabled as defense in depth.
- Caddy obtains HTTPS certificates for a user-supplied domain. Secrets live in ignored `.env.production`; the tracked example contains placeholders only.
- Provide `pg_dump` backup and documented restore/update/rollback procedures. No automatic database downgrade is provided.

## Verification

- Test Atom parsing, empty/malformed feeds, unsafe links, timeouts, duplicates, replay, provenance, evidence, CLI, and scheduler wiring.
- Run one real RSS collection and the existing LIVE pipeline against PostgreSQL; report actual supply rather than forcing cards.
- Verify the production Compose model, build, migration, persistence restart, health endpoints, LIVE mode, and public/internal routing locally.
- Actual public deployment, DNS/router changes, and production certificate issuance require mini-PC access and a domain; if unavailable, report the exact remaining user actions.
