# Entity Classification

Classification is a small, versioned, auditable rule layer (`classifier-v2`). It checks all returned
Wikidata `instance of` IDs and explicit Korean/English description tokens. Broad types such as human
(`Q5`) are intentionally not treated as category evidence. Korean and English tokens use Unicode
word boundaries rather than arbitrary substrings; counterexamples such as `가수분해` and `선수금`
fall back to review.

`classifier-v2` adds the narrow Wikidata type `Q3220391` (social networking service) to `AI_TECH`.
It does not classify generic humans, businesses, products, newspapers, or arbitrary websites from
their names alone.

Every classification appends an `entity_classifications` history row containing category,
confidence, reason, version, pipeline run, and cutoff timestamp. The entity's current category is a
convenience projection of the latest result.

When rules imply different categories, resolution is stopped with
`CONFLICTING_WIKIDATA_METADATA`. When no rule matches, the classifier returns `OTHER`, confidence
`0.0`, and `NO_MATCH_NEEDS_REVIEW`. It does not guess from search rank, candidate popularity, or news
text.

The live database migration reached `0005`. Pipeline run 6 refreshed the legacy entity from official
Wikidata metadata, retained the full type list and description, and still produced
`OTHER / NO_MATCH_NEEDS_REVIEW` because no narrow category rule matched.
