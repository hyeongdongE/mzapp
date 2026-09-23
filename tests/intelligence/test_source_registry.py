from __future__ import annotations

from app.intelligence.sources import SOURCE_REGISTRY, required_source_keys
from app.models.enums import Source, SourceType


def test_registry_keeps_static_policy_separate_from_runtime_health() -> None:
    geeknews = SOURCE_REGISTRY[Source.GEEKNEWS]

    assert geeknews.source_type is SourceType.COMMUNITY
    assert geeknews.policy.public_summary is False
    assert geeknews.policy.store_full_content is False
    assert not hasattr(geeknews, "last_success_at")
    assert not hasattr(geeknews.policy, "last_failure_at")


def test_registry_enables_exactly_the_five_first_slice_sources() -> None:
    assert set(required_source_keys()) == {
        Source.GEEKNEWS,
        Source.HACKER_NEWS,
        Source.GITHUB_RELEASES,
        Source.OFFICIAL_CLOUDFLARE,
        Source.OFFICIAL_AWS,
    }
    assert SOURCE_REGISTRY[Source.GOOGLE_TRENDS].enabled is False
    assert SOURCE_REGISTRY[Source.WIKIMEDIA].enabled is False


def test_geeknews_public_policy_is_attribution_and_link_only() -> None:
    policy = SOURCE_REGISTRY[Source.GEEKNEWS].policy

    assert policy.public_title is True
    assert policy.public_link is True
    assert policy.public_attribution is True
    assert policy.public_summary is False
