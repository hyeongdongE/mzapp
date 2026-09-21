# GeekNews LIVE verification — 2026-09-21

This record captures the real PostgreSQL verification performed for the official GeekNews Atom
feed. It is operational evidence, not a promise of card supply. Thresholds, category states,
evidence requirements, and manual approval were not relaxed.

## Source and provenance

- Endpoint: `https://news.hada.io/rss/news`
- Access: official Atom feed only; no HTML, comments, users, login, or private endpoint
- HTTP result: 200, `application/atom+xml`
- Raw payload: 43,786 bytes, SHA-256
  `1563d7a6db853cc601775fefdac7537689a41781c52df2e6e7ecda4811f057d3`
- Stored provenance: raw payload, source timestamp, observed/collected time, request URL,
  collector version, parser version, and payload hash
- Parser correction: v2 decodes HTML entities contained in CDATA; replay preserves the distinct
  v1 and v2 semantics rather than rewriting history
- Replay dry-run digest:
  `6d9d55521a646f3caf2106ea9a4c95bb18ebad335422842393056cab84668017`

## Real collection and pipeline

| Measurement | Result |
| --- | ---: |
| Latest corrected collection run | 480 / SUCCEEDED |
| RSS items / observations | 50 |
| Unique candidates from run 480 | 50 |
| Resolved entities | 0 |
| AI_TECH entities | 0 |
| Publishable WHAT | 0 |
| Publishable INTEREST | 0 |
| Approved GeekNews cards | 0 |
| Pipeline run | 26 / LIVE / SUCCEEDED |

The blocker is exact entity resolution: current GeekNews titles are article-shaped sentences, and
none matched an exact Wikidata entity. The integration therefore produced no GeekNews card. No
title-splitting/NLP extractor was added because that would exceed the minimal integration scope;
no candidate was manually recategorized or approved.

The existing approved LIVE path remained healthy. With `DEMO_MODE_ENABLED=false`, the public Feed
returned three eligible snapshots named `인스타그램`, and browser/API smoke checks covered Feed,
Detail, Save, Saved, and Feedback. These existing cards use Google Trends and Wikidata evidence,
not GeekNews, and are not counted as GeekNews supply.

## Scope note: classifier baseline

The branch also contains `classifier-v2` mapping Wikidata type `Q3220391` (social networking
service) to the existing `AI_TECH` category. That change was implemented and independently reviewed
under the immediately preceding, explicitly approved LIVE classification task. It is inherited
baseline work, not a GeekNews-based category rule, taxonomy expansion, or source shortcut. GeekNews
items still use the same deterministic classifier and receive no category merely because their
source is GeekNews.

## Verification summary

- Backend: 252 passed, 14 skipped (optional external/PostgreSQL gates)
- PostgreSQL integration on a separately migrated database: 11 passed
- Frontend: 13 passed; TypeScript, ESLint, production build passed
- Production Compose: parsed, built, migrated fresh to `0010`, and retained migration/data across
  a DB/API restart
- Production route smoke: root/health/categories 200; public internal/OpenAPI 404; loopback
  internal 200; LIVE mode; secure session cookie; foreign-origin mutation 403
- Actual mini PC, DNS/NAT/firewall, and certificate issuance: not executed because host access and
  infrastructure details were not available
