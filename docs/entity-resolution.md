# Candidate and Entity Resolution

## Deterministic candidate generation

- Candidate text uses Unicode NFKC, case-folding, punctuation-to-space conversion, and whitespace
  collapse. Meaning-bearing `+`, `#`, and `&` are retained so names such as C, C++, and C# do not
  collapse. Empty normalized values are rejected. It does not transliterate, stem, or fuzzy-match.
- Candidate identity is exact `(source, normalized_text)`. Every source observation is linked once.
- Rejected or merged candidates are immutable generations. If the same text reappears, a new `NEW`
  generation is created instead of rewriting the earlier review history.
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
pipeline run, cutoff, actual attempt time, candidate, selected entity FK, result/reason, and causally
linked raw-fetch FK rows. A candidate has at most one entity link; a later different QID becomes
`ENTITY_RELINK_CONFLICT` instead of a silent second merge. External strings are treated only as data
and never as instructions.

Entity-stage `REPLAY` is deliberately rejected until Phase 8 provides a historical entity/alias
projection. `LIVE` cutoffs older than five minutes are rejected by both the service and resolver
before any request, preventing a caller from backdating current Wikidata through a mislabeled live
run. Cutoffs more than five minutes in the future are rejected as well. This prevents a past cutoff
from consulting current Wikidata or aliases learned later and keeps cutoff/event ordering coherent.

Entity, alias, candidate, and entity-link get-or-create operations use database uniqueness plus
savepoint recovery. PostgreSQL concurrency tests cover both duplicate QID creation and two complete
resolvers racing to add the same aliases while linking separate source candidates.

## Migration 0005 integrity preflight

`0005` never guesses which entity is correct if a pre-fix `0004` database already contains multiple
entity links for one candidate. It aborts transactionally with the exact `candidate_id`, leaving the
database at `0004` and all links intact. Review that candidate, retain exactly one correct
`entity_candidates` row (or remove all links to force later review), then rerun the migration.
Downgrade likewise refuses to collapse multiple candidate generations into the older schema; resolve
those generations explicitly before downgrading. Both fail-fast paths preserve data rather than
silently choosing or deleting it.

## Live smoke (2026-09-20)

The stored official observations produced 32 source-scoped candidates at cutoff
`2026-09-20T15:00:00Z`. Post-review pipeline run 6 made exactly one official Wikidata search/get pair,
retained both raw responses as fetches 11 and 12, linked them to one resolution attempt, refreshed all
four returned `instance of` IDs plus the description, classified conservatively as `OTHER`, and
completed as `SUCCEEDED`. DB inspection showed the distinct cutoff, actual attempt time, selected
entity FK, and raw-fetch FK rows. A stale-cutoff execution exited nonzero, made zero new Wikidata
fetches, and created zero pipeline runs. The one-candidate cap is a polite smoke-test option only.
