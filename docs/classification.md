# Entity Classification

Classification is a small, versioned, auditable rule layer (`classifier-v1`). It checks a narrow
allowlist of Wikidata `instance of` IDs first, then explicit Korean/English description tokens. Broad
types such as human (`Q5`) are intentionally not treated as category evidence.

Every classification appends an `entity_classifications` history row containing category,
confidence, reason, version, pipeline run, and cutoff timestamp. The entity's current category is a
convenience projection of the latest result.

When no rule matches, the classifier returns `OTHER`, confidence `0.0`, and
`NO_MATCH_NEEDS_REVIEW`. It does not guess from search rank, candidate popularity, or news text.

The live database migration reached `0003`. Re-running the entity pipeline appended a classification
for the pre-migration entity; because that legacy row had no stored description, it correctly fell
back to `OTHER / NO_MATCH_NEEDS_REVIEW` rather than inventing a category.
