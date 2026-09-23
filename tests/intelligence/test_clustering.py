from __future__ import annotations

import pytest

from app.intelligence.clustering import ClusterAction, ConservativeClusterer
from tests.intelligence.golden.loader import load_golden_dataset


def test_four_sources_for_one_known_event_form_one_cluster() -> None:
    dataset = load_golden_dataset()

    result = ConservativeClusterer().process(
        dataset.items_for("four-source-same-event")
    )

    assert len(result.clusters) == 1
    assert result.clusters[0].source_count == 4
    assert all(
        decision.action in {ClusterAction.NEW, ClusterAction.MERGE}
        for decision in result.decisions
    )


@pytest.mark.parametrize(
    "group",
    [
        "same-entity-different-event",
        "same-day-different-release",
        "follow-up-vs-new-event",
        "title-collision-hard-negative",
        "product-name-collision",
    ],
)
def test_hard_negatives_do_not_auto_merge(group: str) -> None:
    dataset = load_golden_dataset()

    result = ConservativeClusterer().process(dataset.items_for(group))

    assert result.incorrect_merge_count == 0
    assert all(
        decision.action in {ClusterAction.NEW, ClusterAction.REVIEW}
        for decision in result.decisions
    )


def test_ambiguous_same_entity_signal_requires_review_without_mutating_cluster() -> None:
    dataset = load_golden_dataset()
    items = dataset.items_for("title-collision-hard-negative")[:2]

    result = ConservativeClusterer().process(items)

    assert len(result.clusters) == 2
    assert result.decisions[-1].action is ClusterAction.REVIEW
