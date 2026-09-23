from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.intelligence.evidence import evidence_from_raw_item
from app.models.enums import EvidenceKind, Source

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def raw_item(source: Source) -> SimpleNamespace:
    return SimpleNamespace(
        source=source,
        external_id="source:1",
        title="A material release",
        url="https://source.example/item/1",
        canonical_url="https://vendor.example/release/1",
        published_at=NOW,
        collected_at=NOW,
        item_metadata={"attribution": "Source"},
    )


def test_official_feed_is_official_evidence_without_changing_importance() -> None:
    evidence = evidence_from_raw_item(raw_item(Source.OFFICIAL_CLOUDFLARE))

    assert evidence.kind is EvidenceKind.OFFICIAL
    assert evidence.fact["title"] == "A material release"
    assert "importance" not in evidence.fact


def test_maintainer_release_is_developer_evidence() -> None:
    evidence = evidence_from_raw_item(raw_item(Source.GITHUB_RELEASES))

    assert evidence.kind is EvidenceKind.DEVELOPER
    assert evidence.source_url == "https://source.example/item/1"
