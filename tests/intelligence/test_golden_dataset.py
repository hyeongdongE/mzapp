from __future__ import annotations

from app.intelligence.deduplication import Deduplicator, DuplicateKind
from tests.intelligence.golden.loader import load_golden_dataset


def test_golden_dataset_has_required_positive_and_hard_negative_groups() -> None:
    dataset = load_golden_dataset()

    assert len(dataset.items) >= 50
    assert dataset.group("four-source-same-event").expected_cluster_count == 1
    assert dataset.group("same-entity-different-event").expected_cluster_count >= 2
    assert dataset.group("same-day-different-release").expected_cluster_count >= 2
    assert dataset.group("follow-up-vs-new-event").expected_cluster_count >= 2


def test_golden_duplicate_labels_have_zero_hard_negative_false_matches() -> None:
    dataset = load_golden_dataset()
    deduplicator = Deduplicator()

    for group in dataset.groups:
        items = dataset.items_for(group.name)
        for index, candidate in enumerate(items):
            decision = deduplicator.decide(candidate, items[:index])
            if candidate.duplicate_of is None:
                assert decision.kind is DuplicateKind.DISTINCT, (
                    group.name,
                    candidate.id,
                    decision,
                )
            else:
                assert decision.kind is DuplicateKind.EXACT
                assert decision.matched_item_id == candidate.duplicate_of
