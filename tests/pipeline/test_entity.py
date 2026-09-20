from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.collectors.base import HttpRequestFailed
from app.collectors.wikidata import WikidataLookup, WikidataMatch
from app.models.enums import CandidateStatus, ResolutionStatus, ReviewStatus, Source
from app.models.tables import EntityAlias, EntityCandidate, TrendCandidate, TrendEntity
from app.pipeline.entity import EntityResolver
from app.pipeline.normalization import normalize_text
from app.repositories.entities import EntityRepository

AS_OF = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def candidate(db_session, text: str) -> TrendCandidate:
    value = TrendCandidate(
        source=Source.GOOGLE_TRENDS,
        canonical_text=text,
        normalized_text=normalize_text(text),
        first_seen_at=AS_OF,
        last_seen_at=AS_OF,
        status=CandidateStatus.NEW,
        resolution_status=ResolutionStatus.NEEDS_REVIEW,
        normalizer_version="normalizer-v1",
    )
    db_session.add(value)
    db_session.flush()
    return value


class FakeWikidata:
    def __init__(self, matches=None, error: Exception | None = None, *, complete: bool = True):
        self.matches = matches or []
        self.error = error
        self.complete = complete

    async def lookup(self, _query: str) -> WikidataLookup:
        if self.error:
            raise self.error
        return WikidataLookup(matches=self.matches, raw_responses=[], complete=self.complete)


def resolver(db_session, wikidata, *, now: datetime = AS_OF) -> EntityResolver:
    return EntityResolver(db_session, wikidata, now=lambda: now)


@pytest.mark.asyncio
async def test_exact_stored_alias_resolves_without_wikidata(db_session):
    repo = EntityRepository(db_session)
    entity = repo.create_entity(
        canonical_name="이현중",
        normalized_name="이현중",
        wikidata_id="Q123",
        entity_type="human",
    )
    repo.add_alias(entity.id, "Lee Hyunjung", "en", source="HUMAN", approved=True)

    result = await resolver(db_session, FakeWikidata()).resolve(
        candidate(db_session, "lee hyunjung"), AS_OF
    )

    assert result.entity_id == entity.id
    assert result.status is ResolutionStatus.RESOLVED
    assert result.reason == "EXACT_STORED_ALIAS"


@pytest.mark.asyncio
async def test_same_exact_label_multiple_wikidata_items_needs_review(db_session):
    matches = [
        WikidataMatch("Q1", "김민수", (), "대한민국의 배우", ("Q5",)),
        WikidataMatch("Q2", "김민수", (), "대한민국의 축구 선수", ("Q5",)),
    ]

    result = await resolver(db_session, FakeWikidata(matches)).resolve(
        candidate(db_session, "김민수"), AS_OF
    )

    assert result.entity_id is None
    assert result.status is ResolutionStatus.NEEDS_REVIEW
    assert result.reason == "AMBIGUOUS_WIKIDATA"


@pytest.mark.asyncio
async def test_unapproved_imported_alias_cannot_bypass_homonym_check(db_session):
    repo = EntityRepository(db_session)
    entity = repo.create_entity(
        canonical_name="김민수 배우",
        normalized_name="김민수 배우",
        wikidata_id="Q1",
        entity_type="Q5",
    )
    repo.add_alias(entity.id, "김민수", "ko", source="WIKIDATA_ALIAS", approved=False)
    matches = [
        WikidataMatch("Q1", "김민수", (), "대한민국의 배우", ("Q5",)),
        WikidataMatch("Q2", "김민수", (), "대한민국의 축구 선수", ("Q5",)),
    ]

    result = await resolver(db_session, FakeWikidata(matches)).resolve(
        candidate(db_session, "김민수"), AS_OF
    )

    assert result.status is ResolutionStatus.NEEDS_REVIEW
    assert result.reason == "AMBIGUOUS_WIKIDATA"


@pytest.mark.asyncio
async def test_truncated_exact_wikidata_search_needs_review(db_session):
    match = WikidataMatch("Q1", "김민수", (), "대한민국의 배우", ("Q5",))
    result = await resolver(
        db_session, FakeWikidata([match], complete=False)
    ).resolve(candidate(db_session, "김민수"), AS_OF)

    assert result.status is ResolutionStatus.NEEDS_REVIEW
    assert result.reason == "TRUNCATED_WIKIDATA"


@pytest.mark.asyncio
async def test_conflicting_wikidata_type_and_description_needs_review(db_session):
    match = WikidataMatch("Q1", "이현중", (), "대한민국의 농구 선수", ("Q11424",))
    result = await resolver(db_session, FakeWikidata([match])).resolve(
        candidate(db_session, "이현중"), AS_OF
    )

    assert result.status is ResolutionStatus.NEEDS_REVIEW
    assert result.reason == "CONFLICTING_WIKIDATA_METADATA"


@pytest.mark.asyncio
async def test_single_exact_wikidata_match_creates_aliases_and_link(db_session):
    match = WikidataMatch(
        "Q123",
        "이현중",
        ("Lee Hyunjung", "이현중 농구"),
        "대한민국의 농구 선수",
        ("Q5",),
    )
    value = candidate(db_session, "이현중 농구")

    result = await resolver(db_session, FakeWikidata([match])).resolve(value, AS_OF)

    assert result.status is ResolutionStatus.RESOLVED
    entity = db_session.scalar(select(TrendEntity).where(TrendEntity.id == result.entity_id))
    assert entity is not None
    assert entity.wikidata_id == "Q123"
    assert entity.description == "대한민국의 농구 선수"
    assert entity.review_status is ReviewStatus.PENDING
    aliases = set(db_session.scalars(select(EntityAlias.alias)))
    assert {"이현중", "Lee Hyunjung", "이현중 농구"} <= aliases
    link = db_session.scalar(select(EntityCandidate))
    assert link is not None
    assert link.match_reason == "EXACT_WIKIDATA"


@pytest.mark.asyncio
async def test_wikidata_unavailable_keeps_candidate_for_review(db_session):
    value = candidate(db_session, "이현중")
    result = await resolver(
        db_session, FakeWikidata(error=HttpRequestFailed("TIMEOUT"))
    ).resolve(value, AS_OF)

    assert result.entity_id is None
    assert result.status is ResolutionStatus.NEEDS_REVIEW
    assert result.reason == "WIKIDATA_UNAVAILABLE"


@pytest.mark.asyncio
async def test_historical_cutoff_never_calls_live_wikidata(db_session):
    class UnexpectedWikidata:
        async def lookup(self, _query: str):
            raise AssertionError("historical cutoff must not call live Wikidata")

    with pytest.raises(ValueError, match="historical entity projection"):
        await resolver(db_session, UnexpectedWikidata()).resolve(
            candidate(db_session, "old"),
            AS_OF.replace(hour=11),
        )


@pytest.mark.asyncio
async def test_existing_candidate_link_cannot_silently_move_to_new_qid(db_session):
    value = candidate(db_session, "Foo")
    first = await resolver(
        db_session, FakeWikidata([WikidataMatch("Q1", "Foo", (), None, ())])
    ).resolve(value, AS_OF)
    second = await resolver(
        db_session, FakeWikidata([WikidataMatch("Q2", "Foo", (), None, ())])
    ).resolve(value, AS_OF)

    assert first.status is ResolutionStatus.RESOLVED
    assert second.status is ResolutionStatus.NEEDS_REVIEW
    assert second.reason == "ENTITY_RELINK_CONFLICT"
    assert list(db_session.scalars(select(EntityCandidate))) != []
    assert len(list(db_session.scalars(select(EntityCandidate)))) == 1
