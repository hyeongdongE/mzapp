# SoloPilot IT Intelligence V0 First Vertical Slice Design

**Status:** Approved design captured for implementation planning  
**Date:** 2026-09-23  
**Canonical base:** Trend Radar User MVP commit `a229c14`  
**Implementation branch:** `codex/solopilot-it-intelligence-v0`

## 1. Purpose

SoloPilot V0 answers one question: **what actually changed in the IT industry today?** It continuously collects a bounded set of IT sources, separates raw source records from their original fetch provenance, consolidates records that describe the same real-world event, validates the available evidence, and publishes a daily three-to-seven-item brief that can be read in at most five minutes.

The first vertical slice must traverse this complete path with real data:

```text
GeekNews + Hacker News + GitHub Releases + Official Feeds
→ RawItem
→ Deduplication
→ EventCluster
→ Evidence / Entity
→ Evidence Confidence / Importance
→ Ranking
→ Publication Gate
→ Daily Brief
→ Today UI
```

This is not a general news feed, a prediction product, or a large-scale crawling platform. The user-facing product name changes to **SoloPilot**, while internal package, repository, Python project, and database names remain unchanged during this slice.

## 2. Scope

### Included

- Source policy registry used by collection and publication code.
- GeekNews Atom collection through its published feed.
- Hacker News collection through the public Firebase API.
- GitHub Releases collection for a small configured repository watchlist.
- Two initially enabled official feeds: Cloudflare Blog RSS and AWS News Blog RSS.
- Existing raw payload, raw fetch, collection-run, and replay provenance.
- Normalized `RawItem` records kept separate from original fetch records.
- Deterministic duplicate detection and conservative event clustering.
- Entity extraction and event-level evidence linkage.
- Separate evidence-confidence and importance decisions.
- Ranking, publication gates, brief versioning, and reading-time enforcement.
- Today API and mobile-first Today UI.
- Internal review support for ambiguous clusters and rejected candidates.
- Golden fixtures and measurable quality evaluation.

### Explicitly excluded

- Long-horizon Trend inference or prediction.
- Radar algorithm expansion beyond preserving the existing route for a later slice.
- Personalization or recommendation learning.
- X, arXiv, Hugging Face, Ask SoloPilot, chatbot, RAG, vector databases, or multi-agent behavior.
- Large-scale site crawling.
- Internal package, repository, database, or Python distribution renaming.
- Destructive migration of existing Trend Radar or Personal Automation data.

## 3. Repository Strategy

The Trend Radar User MVP at `a229c14` is the canonical base because it already has a clean Git history, FastAPI/PostgreSQL/Alembic, replayable collection provenance, evidence and claim linkage, scheduler jobs, internal review, Saved/Feedback, a mobile-first PWA, and a passing baseline of 255 Python tests plus 13 frontend tests.

The previous Personal Automation repository at `C:\autoproject` has no commit, HEAD, or remote and all files are untracked. It remains untouched as an archived, recoverable code asset. No history, tag, or synthetic archive commit will be created there.

All database changes in this slice are additive. Existing Google Trends, Wikimedia, trend scoring, feed, and product tables remain available. Google Trends and Wikimedia are registered as disabled-by-default sources for the new IT Intelligence pipeline; their old collector and replay code is not deleted.

## 4. Source Registry and Policy

The registry is executable configuration, not documentation only. Each source entry defines:

- stable source key and display name;
- source family and evidence class;
- collection method and endpoint;
- authority level;
- enabled state;
- full-content storage policy;
- allowed public fields;
- polling interval and freshness expectation;
- optional repository or feed allowlist;
- last success/failure health state.

Initial source state:

| Source | Method | Default | Evidence class | Storage policy |
|---|---|---:|---|---|
| GeekNews | Published Atom/RSS feed | enabled | COMMUNITY | title, links, author, timestamps, bounded snippet/metadata; no full article |
| Hacker News | Public Firebase API | enabled | COMMUNITY | item fields and metrics; no linked-page body |
| GitHub Releases | REST API, configured repositories only | enabled | DEVELOPER or OFFICIAL | release metadata and bounded release-note excerpt; no repository scraping |
| Cloudflare Blog | Official RSS | enabled | PRIMARY/OFFICIAL | feed metadata and bounded excerpt; no full article |
| AWS News Blog | Official RSS | enabled | PRIMARY/OFFICIAL | feed metadata and bounded excerpt; no full article |
| Google Trends | Existing collector | disabled | EARLY_SIGNAL | preserve existing policy and data |
| Wikimedia | Existing collector | disabled | COMMUNITY/EARLY_SIGNAL | preserve existing policy and data |

The two official feeds satisfy the first-slice limit of two to four stable official sources. Adding another source requires an explicit registry entry and adapter contract test; arbitrary user-provided URLs are not fetched.

The initial external contracts are documented by the source owners: GeekNews publishes its feed at `https://news.hada.io/rss/news`; Hacker News exposes the Firebase API described at `https://github.com/HackerNews/API`; GitHub Releases use `https://docs.github.com/en/rest/releases/releases`; Cloudflare Blog serves `https://blog.cloudflare.com/rss/`; and AWS documents `https://aws.amazon.com/blogs/aws/feed/` as its direct news feed. GitHub API use must also comply with `https://docs.github.com/en/site-policy/github-terms/github-terms-of-service` and configured rate limits.

## 5. Data Model

### Existing provenance retained

`CollectionRun`, `RawPayload`, and `RawFetch` remain the immutable acquisition layer. Raw payloads continue to carry payload hash, collector version, parser version, request URL, collection timestamp, and source timestamp. Replay reparses stored payloads using their recorded parser version.

### New normalized layer

`RawItem` is a normalized source record derived from a `RawFetch`; it never replaces or embeds the original payload.

Minimum fields:

- `id`, `raw_fetch_id`, `source_key`, `external_id`;
- `title`, `url`, `original_url`, `author`;
- `published_at`, `collected_at`;
- `canonical_url`, `content_hash`, `normalized_title`;
- `snippet`, `metadata`;
- `normalizer_version`, `created_at`.

Uniqueness is source-aware and idempotent. A replay may reproduce the same normalized item without creating a duplicate, while a parser-version correction may create a new normalization result with explicit provenance rather than rewriting history silently.

### Event and evidence layer

`EventCluster` represents one real-world change and stores canonical title, summary, status, first/last seen timestamps, clustering version, and review state. A membership table links `RawItem N:1 EventCluster` and records the assignment method, score, reason codes, and whether a human confirmed it.

`Entity` remains distinct from an event. Existing `TrendEntity` assets may be adapted behind an event entity-link table rather than redefined destructively. Entity types are constrained to company, product, technology, project, model, framework, language, research, and person.

`EventEvidence` links an event to a raw item and classifies it as `PRIMARY`, `OFFICIAL`, `DEVELOPER`, `COMMUNITY`, `SECONDARY`, or `EARLY_SIGNAL`. It preserves the source URL and the validated fact fields supported by that source.

### Scoring and publication layer

`EventAssessment` stores separate values for:

- `evidence_confidence`: how well the event's factual claims are supported;
- `importance`: how much the verified change matters to the target reader;
- component breakdown, rule version, and evaluation timestamp.

`DailyBrief` stores brief date in `Asia/Seoul`, version, status, generated/published timestamps, window boundaries, item count, word count, reading time, and actual pipeline statistics. `BriefItem` stores position, event reference, headline, category, what happened, why it matters, Fact, Interpretation, Watch, and a snapshot of ordered source links. Existing `SavedTrend` behavior will be adapted after Today is stable; it is not allowed to distort event ranking in this slice.

## 6. Deduplication and Event Clustering

Deduplication identifies repeated source records; clustering identifies different records about the same event. They are separate stages.

### Deterministic duplicate rules

The following can automatically deduplicate records:

1. identical source and external ID;
2. identical normalized canonical URL;
3. identical original target URL after tracking-parameter removal;
4. identical content hash within a compatible source policy;
5. identical GitHub repository and release ID/tag.

Title exact match alone is insufficient.

### Conservative event assignment

Automatic cluster assignment requires a high-precision event identity signal, such as the same official target/release, a canonical link to the same announcement, or a compatible combination of named entities, action/release identifier, normalized title similarity, and bounded publication-time distance.

The number of sources is never a merge condition. The `4 sources → 1 cluster` case is a Golden Fixture describing one known event represented by four sources. It verifies correct behavior but contributes no merge rule by itself.

Incorrect Merge is treated as more harmful than Duplicate Escape. Thresholds and review policy therefore optimize precision before recall:

- a high-confidence deterministic match may auto-merge;
- an ambiguous match creates an unassigned/review candidate;
- a low-confidence match stays in separate clusters;
- no semantic model may force a merge without explainable supporting features;
- manual split/merge decisions are recorded and replayable.

## 7. Evidence Confidence and Importance

Evidence confidence and importance never share one score or substitute for one another.

### Evidence confidence

Evidence confidence evaluates factual support using deterministic inputs:

- existence and accessibility of source records;
- publication date quality;
- evidence authority class;
- agreement across independently derived source types;
- presence of a primary/official source;
- contradictory or missing fields;
- cluster ambiguity and manual-review state.

A source count alone does not imply confidence, and duplicated syndication does not count as independent corroboration. Candidate states are `REJECTED`, `LOW`, `SUPPORTED`, and `STRONG`. Only `SUPPORTED` or `STRONG` events may be published.

### Importance

Importance evaluates the impact of a supported event using explainable components:

- novelty;
- developer or platform impact;
- breaking-change/security/release significance;
- community interest using raw source metrics;
- source diversity after syndication collapse;
- persistence and recency.

An official but minor update may have high confidence and low importance. A highly discussed rumor may have apparent importance but insufficient confidence and must not be published.

## 8. Synthesis Safety

The synthesis input is limited to a validated fact set and its allowed evidence. Deterministic code supplies source existence, URLs, publication dates, official status, GitHub release identifiers, and HN metrics. The synthesis component may classify, summarize, and interpret but cannot invent or override these fields.

Every Brief Item separates:

- **FACT:** evidence-supported, concrete statements;
- **INTERPRETATION:** bounded explanation of why the change may matter;
- **WATCH:** a clearly non-factual observation to monitor.

Specific names, dates, versions, prices, scores, and quantitative claims not present in the validated fact set fail validation. An evidence-only deterministic synthesizer is the required fallback when no LLM provider is configured. The existing real-LLM-disabled default remains safe and testable.

## 9. Ranking and Publication Gate

Ranking runs only after confidence validation. It orders publishable events by importance and tie-breaks deterministically using confidence, recency, and stable event ID. It does not promote an unsupported event because of a high importance score.

The candidate selector returns between three and seven items:

- fewer than three qualifying events: do not publish; mark the brief `INSUFFICIENT_SIGNAL` for review;
- three to seven qualifying events: publish all selected within the reading-time limit;
- more than seven: publish the highest-ranked seven before length reduction;
- no rule forces exactly five items.

Reading time is a publication gate, not decorative metadata. It is calculated from rendered Korean/Latin word and character counts using a versioned algorithm. The target is three to five minutes, and the hard limit is 300 seconds. Synthesis first applies bounded field-level shortening; if the brief still exceeds 300 seconds, the lowest-ranked item is removed while at least three remain. A brief still over the limit, or reduced below three items, is rejected for review rather than published.

Other publication failures include missing sources, invalid or missing dates, unsupported factual claims, unresolved ambiguous clusters, duplicate events in the same brief, invalid source URLs, and stale window boundaries.

## 10. Daily Window and Scheduling

All stored timestamps remain timezone-aware UTC. Brief date and delivery schedule use `Asia/Seoul`. The default brief window is the previous 24 hours at window close.

Proposed configurable schedule:

- collectors: every 15 minutes, with per-source backoff and health recording;
- event processing: after successful collection batches;
- daily window close/ranking: 07:30 Asia/Seoul;
- synthesis and quality gate: 07:45;
- publish: 08:00.

Jobs are idempotent by source/run key, brief date/version, and pipeline version. One failed collector cannot suppress other collectors. A failed publication preserves its candidate set and diagnostics for internal review.

## 11. APIs and Today UI

The public API exposes the latest published brief and an explicitly dated brief. Draft, rejected, and review-only records never appear in the public endpoint. Responses include actual collection statistics and reading time computed from stored data.

The user-facing routes become:

- `/today`: default route and the first-slice value surface;
- `/radar`: preserved shell/placeholder backed only by existing observed activity, with no new inference;
- `/saved`: existing capability retained;
- `/settings`: existing capability retained and later extended with source, language, timezone, and notification time.

Today presents date, “오늘의 IT 5분,” one-line summary, ranked Brief Items, and actual analysis statistics. It has no infinite scroll. Items have unequal visual emphasis by rank, show Fact/Interpretation/Watch distinctly, and provide accessible source links. Existing internal routes remain available under `/internal` for source health, ambiguous clusters, rejected candidates, brief preview, and publication state.

## 12. Error Handling and Operations

- Network collection failures record source health and retry with bounded exponential backoff.
- Malformed payloads fail that source run without corrupting previously stored items.
- Rate limits honor provider retry metadata and never trigger broad scraping fallback.
- Parser changes are versioned and replayed against stored raw payloads.
- Event processing is transactional per pipeline stage and idempotent on retry.
- Ambiguous clustering is an expected review state, not an exception.
- Source correction or deletion updates current evidence state without deleting historical brief snapshots.
- All externally visible statistics come from persisted records; demo fixtures never enter LIVE briefs.

## 13. Testing and Quality Evaluation

TDD is mandatory for implementation. The first slice includes:

- source adapter contract tests for GeekNews, HN, GitHub Releases, and both official feeds;
- policy tests that prevent disallowed full-content persistence/display;
- raw-fetch/RawItem separation and parser-version replay tests;
- URL normalization and duplicate tests;
- conservative clustering tests, including explicit non-merge cases;
- the Golden Fixture where four known records for one event become one cluster;
- a Golden Fixture where similar titles describe different events and remain separate;
- entity and evidence classification tests;
- independent evidence-confidence and importance tests;
- ranking and deterministic tie-break tests;
- unsupported-claim, date, source, ambiguity, duplicate-event, item-count, and reading-time publication-gate tests;
- brief versioning and scheduler idempotency tests;
- API and Today UI tests, including source-link preservation and accessibility;
- existing backend and frontend regression suites.

The Golden Dataset begins with at least 50 versioned RawItems covering expected duplicates, non-duplicates, clusters, entities, confidence, importance, and brief inclusion. Quality reporting records:

- Incorrect Merge Rate as the primary clustering safety metric;
- Duplicate Escape Rate;
- Unclustered Rate;
- Unsupported Claim Rate;
- Brief Item Acceptance Rate;
- Source Coverage;
- actual Reading Time.

Incorrect Merge has the strictest release threshold: no known incorrect merge is permitted in the Golden Dataset. A duplicate escape can be reviewed or corrected without combining unrelated facts, so it is treated as the lower-severity failure.

## 14. Migration and Rollback

The implementation starts from `a229c14` on `codex/solopilot-it-intelligence-v0`. Alembic migrations only add new tables, indexes, enums, or nullable linkage required by the slice. Existing migrations and stored records are never rewritten or dropped.

Rollback consists of disabling the new scheduler and public Today route while leaving new tables intact for diagnosis. The previous Trend Radar branches and `C:\autoproject` Personal Automation code remain untouched. User-facing branding changes can be reverted independently from data migrations.

## 15. Exit Criteria

The slice is complete only when:

1. all five initially enabled adapters collect real data or produce explicit source-health failures;
2. normalized RawItems retain links to immutable raw fetch provenance;
3. deduplication and conservative clustering pass the Golden Dataset with zero known incorrect merges;
4. the four-source same-event fixture produces exactly one EventCluster without using source count as a rule;
5. entities and evidence are linked to each event;
6. evidence confidence and importance are computed and stored separately;
7. ranking selects only confidence-qualified events;
8. publication emits three to seven distinct events and rejects output over five minutes;
9. every published item contains Fact, Interpretation, Watch, and source links;
10. `/today` renders the latest published brief and real analysis statistics;
11. collection-to-Today succeeds on a real-data run;
12. all new tests and the existing regression suites pass;
13. actual quality results and limitations are documented without fabricated metrics.
