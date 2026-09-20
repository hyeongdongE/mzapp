# Evidence-grounded summaries

Phase 5 generates deterministic summaries from persisted official-source evidence. It does not call
an LLM or a Meta API.

## Flow

1. Select resolved entities from the top `N` snapshots at the exact `as_of` and `score_version`.
2. Materialize `TREND_SIGNAL` evidence only from linked observations whose source and acquisition
   timestamps are no later than `as_of`.
3. Materialize `WIKIDATA_ENTITY` evidence only when its resolution attempt, raw fetch, and raw
   payload were already available by `as_of`. The fact is reparsed from those immutable raw bytes;
   mutable current entity metadata is never copied into historical evidence.
4. Build structured `WHAT`, `INTEREST`, and `CAUSE` drafts with evidence IDs.
5. Reject missing IDs, entity mismatches, future evidence, future source timestamps, non-HTTPS or
   non-allowlisted source URLs, claim/evidence-kind mismatches, and claim text that does not match
   the deterministic evidence rendering or explicit trusted causal fact before persistence.
6. Persist every checked draft with its support status and `publishable` flag. Evidence rows retain
   exact observation or resolution-attempt/raw-fetch FKs, while claim-to-snapshot links preserve the
   scoring occurrence. Cache results, including empty results, by entity, canonical evidence-set
   hash, and prompt version.

`SUPPORTED` claims are publishable. `UNSUPPORTED` and `CONTRADICTED` claims are not. The current PoC
does not opt any `PARTIALLY_SUPPORTED` claim into publication.

## Cause handling

Google Trends and Wikimedia traffic signals establish interest, not cause. They cannot support a
causal assertion. With no explicit trusted `CAUSAL_EVENT`, the deterministic provider emits exactly:

> 관심 증가는 확인되었지만 증가 원인은 확인되지 않았습니다.

This fixed epistemic statement is linked to the interest evidence and is publishable; an arbitrary
causal sentence backed only by traffic evidence remains `UNSUPPORTED`.

External titles and text are data only. The deterministic provider never follows embedded
instructions or URLs, and `requested_urls` is always empty. Evidence URLs must use HTTPS and the
source-specific official host allowlist.

## Disabled optional providers

- `DisabledLlmSummaryProvider` raises `ProviderDisabled` before invoking an injected transport.
- Instagram hashtag, Instagram Business Discovery, and Threads keyword providers return
  `DISABLED` with no evidence and make no request.
- `LLM_PROVIDER_ENABLED=false` and `META_PROVIDER_ENABLED=false` remain the safe configuration.

## Run

From a native Windows shell, point the process at the published Docker PostgreSQL port explicitly:

```powershell
$env:DATABASE_URL='postgresql+psycopg://trend_radar:trend_radar@127.0.0.1:5432/trend_radar'
uv run python scripts/generate_summaries.py --top-n 20
```

The Phase 5 live verification returned `snapshots=0 claims=0 provider=evidence-only`; direct database
inspection confirmed zero evidence and claim rows because Phase 4 intentionally suppressed the only
resolved structural Wikimedia entity. This is an eligible-input result, not a provider failure.

Legacy claims that predate snapshot/raw provenance cannot be reconstructed safely. Migration `0008`
therefore marks any claim without a snapshot link `UNSUPPORTED` and non-publishable and removes its
cache entry; it never guesses a historical source.

Verification after independent-review fixes: 123 tests passed, 11 opt-in integration tests skipped,
and Ruff passed. A fresh PostgreSQL database migrated through `0008` and persisted two supported
claims with exact evidence and snapshot links. A separate `0005 -> 0008` fixture proved a legacy
publishable WHAT claim is quarantined. Both temporary databases were removed after inspection.
