from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.collectors.wikidata import WikidataLookup, WikidataMatch, WikidataRawResponse
from app.models.enums import RunStatus
from app.models.tables import PipelineRun, RawFetch, TrendEntity
from app.services.pipeline import PipelineService, observations_for_replay
from tests.pipeline.test_candidate import AS_OF, add_observation


def test_observations_for_replay_enforces_cutoff_and_order(db_session) -> None:
    before = add_observation(
        db_session, item_id="before", text="before", source_timestamp=AS_OF - timedelta(minutes=1)
    )
    add_observation(
        db_session, item_id="after", text="after", source_timestamp=AS_OF + timedelta(minutes=1)
    )
    add_observation(
        db_session,
        item_id="learned-later",
        text="learned later",
        source_timestamp=AS_OF - timedelta(days=1),
        observed_at=AS_OF + timedelta(minutes=1),
    )

    results = observations_for_replay(db_session, AS_OF)

    assert [observation.id for observation in results] == [before.id]


def test_observations_for_replay_rejects_naive_or_non_utc_cutoff(db_session) -> None:
    with pytest.raises(ValueError, match="aware UTC"):
        observations_for_replay(db_session, datetime(2026, 9, 20, 12, 0))
    with pytest.raises(ValueError, match="aware UTC"):
        observations_for_replay(
            db_session,
            datetime(2026, 9, 20, 12, 0, tzinfo=timezone(timedelta(hours=9))),
        )


@pytest.mark.asyncio
async def test_pipeline_persists_versions_entity_and_wikidata_raw_fetches(db_session) -> None:
    add_observation(db_session, item_id="entity", text="이현중", source_timestamp=AS_OF)

    class FakeWikidata:
        collector_version = "wikidata-api-v1"

        async def lookup(self, _query: str) -> WikidataLookup:
            return WikidataLookup(
                matches=[
                    WikidataMatch(
                        "Q123",
                        "이현중",
                        ("Lee Hyunjung",),
                        "대한민국의 농구 선수",
                        ("Q5",),
                    )
                ],
                raw_responses=[
                    WikidataRawResponse(
                        "https://www.wikidata.org/w/api.php?action=wbsearchentities",
                        b'{"search":[]}',
                        AS_OF,
                    )
                ],
            )

    run = await PipelineService(
        db_session,
        FakeWikidata(),
        now=lambda: AS_OF + timedelta(seconds=1),
    ).build_entities(AS_OF)

    assert run.status is RunStatus.SUCCEEDED
    assert run.normalizer_version == "normalizer-v1"
    assert db_session.scalar(select(func.count()).select_from(PipelineRun)) == 1
    assert db_session.scalar(select(func.count()).select_from(TrendEntity)) == 1
    assert db_session.scalar(select(func.count()).select_from(RawFetch)) == 1
