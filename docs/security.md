# Security and data-policy boundaries

## External data

- Outbound HTTPS is allowlisted to `trends.google.com`, `wikimedia.org`, and
  `www.wikidata.org`/`wikidata.org`; redirects to arbitrary hosts are refused.
- Requests use bounded timeouts, response sizes, retry counts, and exponential backoff.
- RSS/JSON/XML text is data, never an instruction. Embedded news/evidence URLs are displayed but
  never fetched by the collector or summarizer.
- XML parsing rejects malformed input, DTD/entity expansion, oversized bodies, and misleading
  `Content-Length` values. Failures store typed redacted codes rather than raw response bodies.
- Only official Google Trends RSS, Wikimedia Analytics API, and read-only Wikidata API are enabled.
  Every other source in the product brief remains forbidden or `DISABLED`.

## AI and optional providers

The default summary provider is deterministic and evidence-only. Claims fail closed when evidence
is missing, future-dated, entity-mismatched, contradictory, or from an unapproved host. External text
cannot select tools or trigger URL retrieval. `LLM_PROVIDER_ENABLED=false` and
`META_PROVIDER_ENABLED=false` are the supported PoC settings; named Meta providers return
`DISABLED` without network access.

## Secrets and dashboard

- `.env` is ignored. `.env.example` contains no credential.
- Dashboard API keys use `SecretStr` and are not printed in settings representations.
- Docker publishes the dashboard only on host `127.0.0.1`. Public bind is outside the PoC; the app
  refuses it unless both an explicit allow flag and non-empty external API key are present.
- The health endpoint discloses only `{"status":"ok"}`.
- Review writes use a row lock, optimistic entity version, one transaction, and append-only audit.

## Stored data and privacy

The PoC stores official aggregate trend/page data, Wikidata metadata, review actor labels, and cost
facts. It does not collect consumer names, email, phone, precise location, contacts, social account,
or advertising identifiers. Review actor values are internal operational identifiers, not user
profiles.

## Reproducibility and integrity

- Raw bytes are content-addressed and retained with acquisition/source timestamps and versions.
- Both source and acquisition timestamps must pass every historical cutoff.
- Replay uses immutable successful live resolution attempts, not current mutable entity links.
- Persisted replay cannot claim a snapshot owned by another run; cutoff/version collisions fail.
- Trend Score is always presented as an internal relative score, never a probability.
