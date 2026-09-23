from __future__ import annotations

from types import SimpleNamespace

from app.intelligence.deduplication import Deduplicator, DuplicateKind
from app.models.enums import Source


def item(
    item_id: int,
    *,
    source: Source = Source.HACKER_NEWS,
    external_id: str | None = None,
    canonical_url: str | None = None,
    content_hash: str | None = None,
    normalized_title: str = "same-looking title",
    metadata: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=item_id,
        source=source,
        external_id=external_id or f"external-{item_id}",
        canonical_url=canonical_url or f"https://example.com/events/{item_id}",
        content_hash=content_hash or f"hash-{item_id}",
        normalized_title=normalized_title,
        item_metadata=metadata or {},
    )


def test_same_source_external_id_is_exact_duplicate() -> None:
    existing = item(7, external_id="hn:123")
    candidate = item(8, external_id="hn:123")

    decision = Deduplicator().decide(candidate, [existing])

    assert decision.kind is DuplicateKind.EXACT
    assert decision.matched_item_id == 7
    assert decision.reason_codes == ("SAME_SOURCE_EXTERNAL_ID",)


def test_canonical_url_ignores_tracking_only_differences() -> None:
    existing = item(3, canonical_url="https://vendor.example/releases/1")
    candidate = item(
        4,
        source=Source.GEEKNEWS,
        canonical_url="https://vendor.example/releases/1?utm_source=feed#top",
    )

    decision = Deduplicator().decide(candidate, [existing])

    assert decision.kind is DuplicateKind.EXACT
    assert decision.reason_codes == ("SAME_CANONICAL_URL",)


def test_identical_content_hash_is_exact_duplicate() -> None:
    decision = Deduplicator().decide(
        item(5, content_hash="shared-hash"),
        [item(2, content_hash="shared-hash")],
    )

    assert decision.kind is DuplicateKind.EXACT
    assert decision.reason_codes == ("SAME_CONTENT_HASH",)


def test_github_repository_and_release_id_are_exact_identity() -> None:
    identity = {"repository": "acme/sdk", "release_id": 901}
    decision = Deduplicator().decide(
        item(9, source=Source.GITHUB_RELEASES, metadata=identity),
        [item(6, source=Source.GITHUB_RELEASES, metadata=identity)],
    )

    assert decision.kind is DuplicateKind.EXACT
    assert decision.reason_codes == ("SAME_GITHUB_RELEASE",)


def test_title_similarity_alone_never_marks_duplicate() -> None:
    decision = Deduplicator().decide(
        item(12, normalized_title="acme launches agent"),
        [item(11, normalized_title="acme launches agent")],
    )

    assert decision.kind is DuplicateKind.DISTINCT
    assert decision.matched_item_id is None
    assert decision.reason_codes == ("NO_DETERMINISTIC_IDENTITY",)


def test_different_github_releases_remain_distinct_despite_similar_titles() -> None:
    candidate = item(
        20,
        source=Source.GITHUB_RELEASES,
        normalized_title="acme sdk release",
        metadata={"repository": "acme/sdk", "release_id": 102},
    )
    existing = item(
        19,
        source=Source.GITHUB_RELEASES,
        normalized_title="acme sdk release",
        metadata={"repository": "acme/sdk", "release_id": 101},
    )

    assert Deduplicator().decide(candidate, [existing]).kind is DuplicateKind.DISTINCT


def test_match_selection_is_deterministic_by_lowest_item_id() -> None:
    candidate = item(30, canonical_url="https://vendor.example/releases/stable")
    matches = [
        item(22, canonical_url=candidate.canonical_url),
        item(17, canonical_url=candidate.canonical_url),
    ]

    decision = Deduplicator().decide(candidate, matches)

    assert decision.matched_item_id == 17
