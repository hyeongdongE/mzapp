from __future__ import annotations

from dataclasses import replace

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
    expected = dataset.group(group)

    result = ConservativeClusterer().process(dataset.items_for(group))

    assert result.incorrect_merge_count == 0
    assert len(result.clusters) == expected.expected_cluster_count


def test_follow_up_without_explicit_identity_does_not_auto_merge() -> None:
    dataset = load_golden_dataset()

    result = ConservativeClusterer().process(dataset.items_for("follow-up-vs-new-event"))

    partitions = {frozenset(item.id for item in cluster.members) for cluster in result.clusters}
    assert all(len(partition) == 1 for partition in partitions)


def test_same_provider_incident_words_do_not_merge_different_targets() -> None:
    dataset = load_golden_dataset()
    source = dataset.items_for("follow-up-vs-new-event")
    api_outage = replace(
        source[0],
        normalized_title="cloudflare api outage",
        event_id="api-outage",
    )
    dashboard_recovery = replace(
        source[1],
        normalized_title="cloudflare dashboard outage resolved",
        event_id="dashboard-outage",
    )

    result = ConservativeClusterer().process([api_outage, dashboard_recovery])

    assert len(result.clusters) == 2
    assert result.incorrect_merge_count == 0


def test_ambiguous_same_entity_signal_requires_review_without_mutating_cluster() -> None:
    dataset = load_golden_dataset()
    items = dataset.items_for("title-collision-hard-negative")[:2]

    result = ConservativeClusterer().process(items)

    assert len(result.clusters) == 2
    assert result.decisions[-1].action is ClusterAction.REVIEW
