# Entity Classification

Classification is a small, versioned, auditable rule layer (`classifier-v1`). It checks all returned
Wikidata `instance of` IDs and explicit Korean/English description tokens. Broad types such as human
(`Q5`) are intentionally not treated as category evidence. English tokens use word boundaries rather
than arbitrary substrings.

Every classification appends an `entity_classifications` history row containing category,
confidence, reason, version, pipeline run, and cutoff timestamp. The entity's current category is a
convenience projection of the latest result.

When rules imply different categories, resolution is stopped with
`CONFLICTING_WIKIDATA_METADATA`. When no rule matches, the classifier returns `OTHER`, confidence
`0.0`, and `NO_MATCH_NEEDS_REVIEW`. It does not guess from search rank, candidate popularity, or news
text.

The live database migration reached `0004`. Pipeline run 5 refreshed the legacy entity from official
Wikidata metadata, retained the full type list and description, and still produced
`OTHER / NO_MATCH_NEEDS_REVIEW` because no narrow category rule matched.
