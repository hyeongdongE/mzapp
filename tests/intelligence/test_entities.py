from __future__ import annotations

from types import SimpleNamespace

from app.intelligence.entities import extract_entities
from app.models.enums import Source


def test_github_repository_extracts_owner_and_product_entities() -> None:
    item = SimpleNamespace(
        source=Source.GITHUB_RELEASES,
        title="Claude Code v2.1.0",
        normalized_title="claude code v2.1.0",
        item_metadata={"repository": "anthropics/claude-code"},
    )

    entities = extract_entities(item)

    assert {(entity.normalized_name, entity.entity_type) for entity in entities} >= {
        ("anthropics", "ORGANIZATION"),
        ("claude code", "PRODUCT"),
    }


def test_curated_aliases_are_deterministic_without_wikidata() -> None:
    item = SimpleNamespace(
        source=Source.OFFICIAL_CLOUDFLARE,
        title="Cloudflare Workers runtime release",
        normalized_title="cloudflare workers runtime release",
        item_metadata={},
    )

    entities = extract_entities(item)

    assert [entity.canonical_name for entity in entities][:2] == [
        "Cloudflare",
        "Cloudflare Workers",
    ]
