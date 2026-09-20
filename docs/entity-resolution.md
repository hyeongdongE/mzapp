# Candidate and Entity Resolution

## Deterministic candidate generation

- Candidate text uses Unicode NFKC, case-folding, punctuation-to-space conversion, and whitespace
  collapse. Meaning-bearing `+`, `#`, and `&` are retained so names such as C, C++, and C# do not
  collapse. Empty normalized values are rejected. It does not transliterate, stem, or fuzzy-match.
- Candidate identity is exact `(source, normalized_text)`. Every source observation is linked once.
- `first_seen_at` and `last_seen_at` come from source timestamps, never wall-clock time.
- Replay includes an observation only when both its source timestamp and acquisition `observed_at`
  are at or before the UTC cutoff.

## Conservative entity resolution

1. Resolve one exact, human-approved stored alias match.
2. Otherwise query only the official read-only Wikidata `wbsearchentities` and `wbgetentities`
   actions.
3. Resolve only one exact label/alias match. Search rank alone is never sufficient.
4. Multiple stored aliases, homonyms, a truncated result set, no exact Wikidata result,
   malformed/unavailable Wikidata, conflicting type/description metadata, and inactive candidates
   remain `NEEDS_REVIEW`.

Imported Wikidata labels and aliases are retained as unapproved evidence and never short-circuit a
later homonym check. Only an explicitly approved alias can do that. Exact Wikidata response bytes,
including partial responses before a later request or parse failure, are stored through the same
hash-addressed raw provenance path as the discovery collectors. Each resolution attempt stores the
pipeline run, candidate, result/reason, and causally linked raw-fetch IDs. External strings are treated
only as data and never as instructions.

Entity-stage `REPLAY` is deliberately rejected until Phase 8 provides a historical entity/alias
projection. This prevents a past cutoff from consulting current Wikidata or aliases learned later.

## Live smoke (2026-09-20)

The stored official observations produced 32 source-scoped candidates at cutoff
`2026-09-20T15:00:00Z`. Post-review pipeline run 5 made exactly one official Wikidata search/get pair,
retained both raw responses as fetches 9 and 10, linked them to one resolution attempt, refreshed all
four returned `instance of` IDs plus the description, classified conservatively as `OTHER`, and
completed as `SUCCEEDED`. The one-candidate cap is a polite smoke-test option only.
