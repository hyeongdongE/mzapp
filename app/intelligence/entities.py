from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.models.enums import Source

CURATED_ALIASES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("cloudflare workers", "Cloudflare Workers", "PRODUCT", ("workers",)),
    ("cloudflare", "Cloudflare", "ORGANIZATION", ()),
    ("amazon web services", "Amazon Web Services", "ORGANIZATION", ("aws",)),
    ("aws", "Amazon Web Services", "ORGANIZATION", ("amazon web services",)),
    ("claude code", "Claude Code", "PRODUCT", ()),
    ("openai codex", "OpenAI Codex", "PRODUCT", ("codex",)),
)
PRODUCT_PATTERN = re.compile(
    r"\b([a-z0-9]+(?:[- ]+[a-z0-9]+)*[- ]+(?:agent|cli|code|model|runtime|sdk))\b"
)


class EntityItem(Protocol):
    source: Source
    title: str
    normalized_title: str
    item_metadata: dict[str, Any]


@dataclass(frozen=True)
class EntityMention:
    canonical_name: str
    normalized_name: str
    entity_type: str
    aliases: tuple[str, ...]
    role: str = "SUBJECT"


def extract_entities(item: EntityItem) -> list[EntityMention]:
    mentions: dict[str, EntityMention] = {}
    text = item.normalized_title.casefold()
    for alias, canonical, entity_type, aliases in CURATED_ALIASES:
        if alias in text or any(value in text for value in aliases):
            normalized = canonical.casefold()
            mentions[normalized] = EntityMention(
                canonical,
                normalized,
                entity_type,
                tuple(sorted({alias, *aliases})),
            )

    repository = item.item_metadata.get("repository")
    if isinstance(repository, str) and "/" in repository:
        owner, product = repository.split("/", 1)
        _add(mentions, owner.replace("-", " "), "ORGANIZATION")
        _add(mentions, product.replace("-", " "), "PRODUCT")

    for match in PRODUCT_PATTERN.finditer(text):
        value = match.group(1).replace("-", " ")
        words = value.split()
        _add(mentions, " ".join(words[-3:]), "PRODUCT")

    if item.source is Source.OFFICIAL_CLOUDFLARE:
        _add(mentions, "Cloudflare", "ORGANIZATION")
    if item.source is Source.OFFICIAL_AWS:
        _add(mentions, "Amazon Web Services", "ORGANIZATION")
    return sorted(mentions.values(), key=lambda mention: mention.normalized_name)


def _add(
    mentions: dict[str, EntityMention], value: str, entity_type: str
) -> None:
    normalized = " ".join(value.casefold().split())
    if normalized and normalized not in mentions:
        mentions[normalized] = EntityMention(
            canonical_name=" ".join(word.capitalize() for word in normalized.split()),
            normalized_name=normalized,
            entity_type=entity_type,
            aliases=(),
        )
