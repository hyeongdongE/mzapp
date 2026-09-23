from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.models.enums import Source, SourceType


@dataclass(frozen=True)
class SourcePolicy:
    store_full_content: bool
    public_title: bool = True
    public_link: bool = True
    public_attribution: bool = True
    public_summary: bool = False


@dataclass(frozen=True)
class SourceDefinition:
    source: Source
    display_name: str
    source_type: SourceType
    collection_method: str
    authority_level: int
    enabled: bool
    policy: SourcePolicy
    expected_freshness: timedelta


PUBLIC_METADATA_ONLY = SourcePolicy(store_full_content=False)

SOURCE_REGISTRY: dict[Source, SourceDefinition] = {
    Source.GEEKNEWS: SourceDefinition(
        source=Source.GEEKNEWS,
        display_name="GeekNews",
        source_type=SourceType.COMMUNITY,
        collection_method="RSS",
        authority_level=2,
        enabled=True,
        policy=PUBLIC_METADATA_ONLY,
        expected_freshness=timedelta(hours=1),
    ),
    Source.HACKER_NEWS: SourceDefinition(
        source=Source.HACKER_NEWS,
        display_name="Hacker News",
        source_type=SourceType.COMMUNITY,
        collection_method="API",
        authority_level=2,
        enabled=True,
        policy=PUBLIC_METADATA_ONLY,
        expected_freshness=timedelta(minutes=30),
    ),
    Source.GITHUB_RELEASES: SourceDefinition(
        source=Source.GITHUB_RELEASES,
        display_name="GitHub Releases",
        source_type=SourceType.DEVELOPER,
        collection_method="API",
        authority_level=4,
        enabled=True,
        policy=PUBLIC_METADATA_ONLY,
        expected_freshness=timedelta(hours=1),
    ),
    Source.OFFICIAL_CLOUDFLARE: SourceDefinition(
        source=Source.OFFICIAL_CLOUDFLARE,
        display_name="Cloudflare Blog",
        source_type=SourceType.OFFICIAL,
        collection_method="RSS",
        authority_level=5,
        enabled=True,
        policy=PUBLIC_METADATA_ONLY,
        expected_freshness=timedelta(hours=6),
    ),
    Source.OFFICIAL_AWS: SourceDefinition(
        source=Source.OFFICIAL_AWS,
        display_name="AWS News Blog",
        source_type=SourceType.OFFICIAL,
        collection_method="RSS",
        authority_level=5,
        enabled=True,
        policy=PUBLIC_METADATA_ONLY,
        expected_freshness=timedelta(hours=6),
    ),
    Source.GOOGLE_TRENDS: SourceDefinition(
        source=Source.GOOGLE_TRENDS,
        display_name="Google Trends",
        source_type=SourceType.EARLY_SIGNAL,
        collection_method="RSS",
        authority_level=1,
        enabled=False,
        policy=PUBLIC_METADATA_ONLY,
        expected_freshness=timedelta(hours=1),
    ),
    Source.WIKIMEDIA: SourceDefinition(
        source=Source.WIKIMEDIA,
        display_name="Wikimedia",
        source_type=SourceType.EARLY_SIGNAL,
        collection_method="API",
        authority_level=1,
        enabled=False,
        policy=PUBLIC_METADATA_ONLY,
        expected_freshness=timedelta(days=1),
    ),
}


def required_source_keys() -> tuple[Source, ...]:
    return tuple(definition.source for definition in SOURCE_REGISTRY.values() if definition.enabled)
