# Candidate and Entity Resolution

## Deterministic candidate generation

- Candidate text uses Unicode NFKC, case-folding, punctuation-to-space conversion, and whitespace
  collapse. It does not transliterate, stem, or fuzzy-match.
- Candidate identity is exact `(source, normalized_text)`. Every source observation is linked once.
- `first_seen_at` and `last_seen_at` come from source timestamps, never wall-clock time.
- Replay includes an observation only when both its source timestamp and acquisition `observed_at`
  are at or before the UTC cutoff.

## Conservative entity resolution

1. Resolve one exact stored alias/name match.
2. Otherwise query only the official read-only Wikidata `wbsearchentities` and `wbgetentities`
   actions.
3. Resolve only one exact label/alias match. Search rank alone is never sufficient.
4. Multiple stored aliases, homonyms, no exact Wikidata result, malformed/unavailable Wikidata, and
   conflicting matches remain `NEEDS_REVIEW`.

Resolved Wikidata labels and aliases are versioned through `entity-v1`; entity review status starts
at `PENDING`. Exact Wikidata response bytes are stored through the same hash-addressed raw provenance
path as the discovery collectors. External strings are treated only as data and never as instructions.

## Live smoke (2026-09-20)

The stored official observations produced 32 source-scoped candidates at cutoff
`2026-09-20T15:00:00Z`. A one-candidate live cap made exactly one Wikidata search/get pair, retained
both raw responses, resolved one entity, and completed pipeline run 1 as `SUCCEEDED`. The cap is a
polite smoke-test option only; an uncapped run processes all candidates.
