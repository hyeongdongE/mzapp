# Official Data Sources

## Google Trends Trending Now RSS

- Official endpoint: `https://trends.google.com/trending/rss?geo=KR`
- Usage: hourly discovery of currently trending Korean search terms
- Stored fields: title, publication timestamp, approximate traffic text, parsed lower bound,
  related news metadata, observation timestamp, official feed URL, raw response hash and bytes
- Attribution: every observation retains a Google Trends URL; dashboard/report presentation must
  identify Google Trends as the source
- Access guidance: no numeric public RSS rate limit is assumed; collection defaults to one
  sequential hourly request with timeout and bounded retry/backoff
- Limitations:
  - `approx_traffic` is a threshold-like approximation, not an exact search count
  - RSS does not expose active state, trend-change percentage, or related queries; these remain null
    or empty rather than being inferred
  - News links are stored as untrusted metadata and are never fetched by the collector
  - The limited-access Google Trends API alpha is not enabled

## Wikimedia Analytics API

- Official endpoint pattern:
  `https://wikimedia.org/api/rest_v1/metrics/pageviews/top-per-country/KR/all-access/{YYYY}/{MM}/{DD}`
- Usage: daily Korea-country top-page observations with a two-day default data lag
- Stored fields: country, access, date, article, project, rank, `views_ceil`, observation timestamp,
  official request URL, raw response hash and bytes
- Attribution/license: Wikimedia Analytics API, CC0 1.0
- Access guidance: send an identifying User-Agent, make sequential requests, obey server throttling,
  and use bounded retry/backoff; no hard-coded numeric rate entitlement is assumed
- Limitations:
  - `views_ceil` is the API's rounded ceiling metric, not an exact pageview count
  - Results include multiple Wikimedia projects and structural pages such as main/search pages
  - Structural and recurring pages are retained in raw data so baseline suppression remains auditable

## Wikidata Wikibase API

- Official endpoint: `https://www.wikidata.org/w/api.php`
- Usage: read-only entity search and metadata lookup during normalization
- Planned stored fields: entity ID, labels, aliases, descriptions, selected instance-of metadata,
  source timestamp, raw response hash and bytes
- Access guidance: identifying User-Agent, sequential calls, timeout and bounded retry/backoff
- Limitations: search rank is never sufficient for automatic merge; ambiguous or conflicting matches
  become `NEEDS_REVIEW`

## Explicitly disabled sources

NAVER APIs, pytrends, TikTok, Reddit, X, YouTube-combined scoring, Instagram/Threads scraping,
browser scraping, private endpoints, and reverse-engineered APIs are not configured or allowlisted.
Meta and real LLM providers remain disabled until credentials, approval, use-case permission, and
rate limits are confirmed.
