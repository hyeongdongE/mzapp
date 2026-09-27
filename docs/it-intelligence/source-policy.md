# SoloPilot IT Intelligence Source Policy

## First Slice registry

Source policy is static configuration. Runtime health is stored separately in `SourceHealth`; a timeout, parser failure, or stale interval never changes what a source is allowed to publish. The dogfood policy disables GitHub Releases. Historical GitHub records are preserved for audit but excluded from new Brief candidates, including mixed-source clusters, until those clusters can be reprocessed without the disabled source.

| Source | Enabled | Type | Acquisition | Public fields | Default summary redistribution |
| --- | --- | --- | --- | --- | --- |
| GeekNews | yes | community | official Atom feed | title, attribution, source link | **false** |
| Hacker News | yes | community | official Firebase API | title, author, discussion/original links, deterministic metrics | false |
| GitHub Releases | no | developer/maintainer | retained manual collector for historical compatibility; not part of `all` or scheduled dogfood | not published in new Briefs | false |
| Cloudflare Blog | yes | official | official RSS | title, attribution, link, publication date | false |
| AWS News Blog | yes | official | official RSS | title, attribution, link, publication date | false |
| Google Trends | no | early signal | existing RSS adapter retained | not published in this slice | false |
| Wikimedia | no | early signal | existing API adapter retained | not published in this slice | false |

The enabled registry contains two official feeds and two community discovery sources. Community-only evidence does not reach `SUPPORTED` confidence, so publication requires official corroboration. This is a narrow four-source pilot, not comprehensive IT trend coverage. A source's own title, author, and date are verified as metadata; the current deterministic synthesis does **not** independently verify every claim in the linked article or provide a substantive article summary. Do not describe it as a fully fact-checked five-minute news digest yet.

## Storage and replay

- `RawFetch`/`RawPayload` preserve immutable acquisition provenance and parser/collector versions.
- `RawItem` is a separate normalized record linked to its exact `RawFetch`.
- Hacker News stores one deterministic envelope with the top-story IDs, every requested item response, and every request URL.
- URL canonicalization removes tracking parameters and fragments but preserves event/release identifiers.
- Replay never relies on a re-fetched or rewritten payload.
- Only a collector that explicitly declares a complete response may advance `covered_through`. Partial responses record failed health instead.
- Collector failures are committed per collector instance and do not stop later sources from running.

## Publication rules

- A source count is never a duplicate or event-merge condition by itself.
- Cross-source evidence remains independently attributable after clustering.
- Every public FACT must link through `EventFactEvidence` to exact `EventEvidence` and `RawItem` rows.
- Confidence evaluates evidence support. Importance evaluates material impact. Neither value substitutes for the other.
- `DEGRADED_SOURCE_COVERAGE` blocks publication. Healthy coverage with only one or two qualifying events produces an intentionally short `LOW_SIGNAL_DAY` brief.
- Reading time is capped at 300 estimated seconds; the estimator is a budget, not a measured human reading duration.
- `/api/public/today` only serves a Brief generated under the current `brief-v2-no-github` policy. It returns 404 until the first new-policy Brief is published; dated historical Briefs remain accessible for audit and may reflect the older source policy.
- `/api/public/discovery` is a separate read-only GeekNews source-metadata projection. It shows at most five current-day titles, published times, and validated GeekNews topic links under the explicit `UNVERIFIED_DISCOVERY` marker. It does not synthesize facts, count as a published Daily Brief, satisfy the five-day quality-validation sample, or bypass the Brief evidence gate. The `/today` UI can show this list while the verified Brief endpoint still returns 404.
- The window closes at 07:30. Generation runs at 07:35, after the 07:30 collection and 07:32 processing jobs, and stores a non-public `DRAFT`. The 08:00 action can regenerate an early degraded result, then revalidates coverage, reading time, and FACT evidence before atomically setting `PUBLISHED` or `LOW_SIGNAL_DAY`.
- Public source links must be HTTPS links on the source-specific approved host before they can be persisted or rendered.
- Brief Items have no save endpoint in Slice 1. The existing `/saved` Trend route remains available unchanged.

## Environment configuration

Only HTTPS URLs on approved hosts are accepted. The defaults are listed in `.env.example`. `GITHUB_RELEASE_REPOSITORIES` remains for legacy/manual collection but is not used by dogfood `all` collection. Operators should use an identifying contact in `USER_AGENT` before live collection. Source-policy change starts a new five-eligible-day validation cohort; do not combine dates across policies.
