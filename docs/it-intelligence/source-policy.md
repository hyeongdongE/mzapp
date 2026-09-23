# SoloPilot IT Intelligence Source Policy

## First Slice registry

Source policy is static configuration. Runtime health is stored separately in `SourceHealth`; a timeout, parser failure, or stale interval never changes what a source is allowed to publish. Health is keyed by `(source, collector_key)`, so each configured GitHub repository has an independent state and one repository cannot overwrite another repository's failure.

| Source | Enabled | Type | Acquisition | Public fields | Default summary redistribution |
| --- | --- | --- | --- | --- | --- |
| GeekNews | yes | community | official Atom feed | title, attribution, source link | **false** |
| Hacker News | yes | community | official Firebase API | title, author, discussion/original links, deterministic metrics | false |
| GitHub Releases | yes | developer/maintainer | official REST API, fixed repository watchlist | release title/tag, repository, maintainer, link | false |
| Cloudflare Blog | yes | official | official RSS | title, attribution, link, publication date | false |
| AWS News Blog | yes | official | official RSS | title, attribution, link, publication date | false |
| Google Trends | no | early signal | existing RSS adapter retained | not published in this slice | false |
| Wikimedia | no | early signal | existing API adapter retained | not published in this slice | false |

The enabled registry contains two stable official feeds, two community sources, and one maintainer-release family. GitHub creates one collector per configured repository; repository order is configuration, not a merge signal. The GitHub collector polls the latest release (`per_page=1`) every 15 minutes to keep the response inside the bounded payload contract.

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
- The window closes at 07:30. Generation runs at 07:35, after the 07:30 collection and 07:32 processing jobs, and stores a non-public `DRAFT`. The 08:00 action can regenerate an early degraded result, then revalidates coverage, reading time, and FACT evidence before atomically setting `PUBLISHED` or `LOW_SIGNAL_DAY`.
- Public source links must be HTTPS links on the source-specific approved host before they can be persisted or rendered.
- Brief Items have no save endpoint in Slice 1. The existing `/saved` Trend route remains available unchanged.

## Environment configuration

Only HTTPS URLs on approved hosts are accepted. The defaults are listed in `.env.example`. `GITHUB_RELEASE_REPOSITORIES` is a JSON array of `owner/name` identifiers. Operators should use an identifying contact in `USER_AGENT` before live collection.
