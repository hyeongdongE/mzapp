from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.enums import Source

FIXTURE = Path(__file__).with_name("raw_items.json")
EXPECTED = Path(__file__).with_name("expected.json")


@dataclass(frozen=True)
class GoldenItem:
    id: int
    source: Source
    external_id: str
    canonical_url: str
    content_hash: str
    normalized_title: str
    item_metadata: dict[str, Any]
    published_at: datetime
    event_id: str
    duplicate_of: int | None
    confidence: str
    importance_rank: int
    brief_included: bool


@dataclass(frozen=True)
class GoldenGroup:
    name: str
    kind: str
    expected_cluster_count: int
    item_ids: tuple[int, ...]


@dataclass(frozen=True)
class GoldenDataset:
    items: tuple[GoldenItem, ...]
    groups: tuple[GoldenGroup, ...]

    def group(self, name: str) -> GoldenGroup:
        return next(group for group in self.groups if group.name == name)

    def items_for(self, name: str) -> list[GoldenItem]:
        ids = set(self.group(name).item_ids)
        return [item for item in self.items if item.id in ids]


def load_golden_dataset() -> GoldenDataset:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    items = tuple(
        GoldenItem(
            id=item["id"],
            source=Source(item["source"]),
            external_id=item["external_id"],
            canonical_url=item["canonical_url"],
            content_hash=item["content_hash"],
            normalized_title=item["normalized_title"],
            item_metadata=item.get("metadata", {}),
            published_at=datetime.fromisoformat(item["published_at"]),
            event_id=item["event_id"],
            duplicate_of=item.get("duplicate_of"),
            confidence=item["confidence"],
            importance_rank=item["importance_rank"],
            brief_included=item["brief_included"],
        )
        for item in payload["items"]
    )
    groups = tuple(
        GoldenGroup(
            name=group["name"],
            kind=group["kind"],
            expected_cluster_count=group["expected_cluster_count"],
            item_ids=tuple(group["item_ids"]),
        )
        for group in expected["groups"]
    )
    _validate(items, groups)
    return GoldenDataset(items=items, groups=groups)


def _validate(items: tuple[GoldenItem, ...], groups: tuple[GoldenGroup, ...]) -> None:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("golden item IDs must be unique")
    known = set(ids)
    grouped = {item_id for group in groups for item_id in group.item_ids}
    if grouped != known:
        raise ValueError("every golden item must belong to exactly one declared group")
    if sum(len(group.item_ids) for group in groups) != len(grouped):
        raise ValueError("golden items cannot belong to multiple groups")
