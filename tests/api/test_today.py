from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.models.enums import BriefStatus, Source
from app.models.tables import BriefItem, DailyBrief
from tests.intelligence.helpers import EvidenceSpec, seed_event

BRIEF_DATE = date(2026, 9, 24)
NOW = datetime(2026, 9, 24, tzinfo=UTC)


def seed_brief(api_session, status: BriefStatus = BriefStatus.PUBLISHED) -> DailyBrief:
    event = seed_event(
        api_session,
        [EvidenceSpec(Source.OFFICIAL_AWS, "Critical security release")],
        suffix=f"api-{status.value}",
    )
    brief = DailyBrief(
        brief_date=BRIEF_DATE,
        version=1,
        status=status,
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
        generated_at=NOW,
        published_at=(
            NOW
            if status in {BriefStatus.PUBLISHED, BriefStatus.LOW_SIGNAL_DAY}
            else None
        ),
        today_in_one_line="보안 업데이트가 오늘의 핵심입니다.",
        raw_item_count=12,
        event_cluster_count=5,
        candidate_count=4,
        selected_count=1,
        word_count=120,
        reading_time_seconds=75,
        generation_version=f"api-{status.value}",
    )
    api_session.add(brief)
    api_session.flush()
    api_session.add(
        BriefItem(
            brief_id=brief.id,
            event_cluster_id=event.id,
            position=1,
            headline="Critical security release",
            category="SECURITY",
            what_happened="중요 보안 릴리스가 공개됐습니다.",
            why_it_matters="즉시 업데이트 검토가 필요합니다.",
            fact_text="버전: v2.0\n발행일: 2026-09-23",
            interpretation_text="해석: 영향 범위를 확인 중입니다.",
            watch_text="관찰: 공식 후속 공지를 확인하세요.",
            source_links=[
                {"title": "AWS", "url": "https://aws.amazon.com/blogs/aws/release"},
                {"title": "GitHub", "url": "https://github.com/acme/tool/releases/2"},
            ],
            importance=90.0,
        )
    )
    api_session.flush()
    return brief


def test_today_returns_latest_public_brief_shape(client, api_session) -> None:
    seed_brief(api_session)

    response = client.get("/api/public/today")

    assert response.status_code == 200
    payload = response.json()
    assert payload["briefDate"] == "2026-09-24"
    assert payload["status"] == "PUBLISHED"
    assert payload["readingTimeSeconds"] == 75
    assert payload["statistics"] == {
        "rawItemCount": 12,
        "eventClusterCount": 5,
        "candidateCount": 4,
        "selectedCount": 1,
    }
    assert payload["items"][0]["sources"][0]["title"] == "AWS"
    assert "factIds" not in payload["items"][0]
    assert "evidenceIds" not in payload["items"][0]


def test_dated_brief_and_low_signal_message(client, api_session) -> None:
    brief = seed_brief(api_session, BriefStatus.LOW_SIGNAL_DAY)
    brief.selected_count = 0
    for item in list(api_session.query(BriefItem).all()):
        api_session.delete(item)
    api_session.flush()

    response = client.get("/api/public/briefs/2026-09-24")

    assert response.status_code == 200
    assert response.json()["status"] == "LOW_SIGNAL_DAY"
    assert response.json()["items"] == []
    assert "기준을 충족" in response.json()["emptyStateMessage"]


def test_absent_or_non_public_brief_is_not_exposed(client, api_session) -> None:
    assert client.get("/api/public/briefs/2026-09-24").status_code == 404
    seed_brief(api_session, BriefStatus.DEGRADED_SOURCE_COVERAGE)

    assert client.get("/api/public/today").status_code == 404
    assert client.get("/api/public/briefs/2026-09-24").status_code == 404
