from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import BriefItem, BriefItemReview, BriefReviewSession
from app.services.brief_quality_review import BriefQualityReviewService
from tests.services.test_brief_quality_review import NOW, seed_brief, valid_item_review


def test_quality_dashboard_requires_today_first_and_starts_review(
    client: TestClient, api_session: Session
) -> None:
    brief = seed_brief(api_session)
    response = client.get("/internal/brief-quality")
    assert response.status_code == 200
    assert "/today" in response.text
    assert "PUBLISHED" in response.text

    started = client.post(
        f"/internal/briefs/{brief.id}/quality-review/start",
        data={"reviewer": "owner"},
        follow_redirects=False,
    )
    assert started.status_code == 303
    page = client.get(started.headers["location"])
    assert "active review effort" in page.text
    assert "제품 읽기 시간이 아닌" in page.text


def test_non_published_brief_cannot_start_review(client: TestClient, api_session: Session) -> None:
    from app.models.enums import BriefStatus

    brief = seed_brief(api_session, status=BriefStatus.DRAFT)
    response = client.post(
        f"/internal/briefs/{brief.id}/quality-review/start",
        data={"reviewer": "owner"},
    )
    assert response.status_code == 409


def test_cross_origin_review_mutation_is_rejected(
    client: TestClient, api_session: Session
) -> None:
    brief = seed_brief(api_session)

    response = client.post(
        f"/internal/briefs/{brief.id}/quality-review/start",
        headers={"Origin": "https://attacker.example"},
        data={"reviewer": "owner"},
    )

    assert response.status_code == 403
    assert api_session.scalar(select(BriefReviewSession)) is None


def test_categorical_item_review_form_round_trips_all_dimensions(
    client: TestClient, api_session: Session
) -> None:
    brief = seed_brief(api_session)
    client.post(
        f"/internal/briefs/{brief.id}/quality-review/start",
        data={"reviewer": "owner"},
    )
    review = api_session.scalar(
        select(BriefReviewSession).where(BriefReviewSession.brief_id == brief.id)
    )
    item = api_session.scalar(select(BriefItem).where(BriefItem.brief_id == brief.id))
    assert review is not None and item is not None

    page = client.get(f"/internal/briefs/{brief.id}/quality-review")
    for field in (
        "usefulness",
        "event_selection",
        "fact_correctness",
        "interpretation_quality",
        "watch_usefulness",
        "verbosity",
        "evidence_set_usefulness",
        "incorrect_merge_verdict",
        "duplicate_escape_verdict",
    ):
        assert f'name="{field}"' in page.text

    response = client.post(
        f"/internal/brief-review-sessions/{review.id}/items/{item.id}",
        data={
            "usefulness": "USEFUL",
            "event_selection": "KEEP",
            "fact_correctness": "CORRECT",
            "interpretation_quality": "STRONG",
            "watch_usefulness": "ACTIONABLE",
            "verbosity": "JUST_RIGHT",
            "evidence_set_usefulness": "ESSENTIAL",
            "incorrect_merge_verdict": "NO_INCORRECT_MERGE",
            "duplicate_escape_verdict": "NO_DUPLICATE_ESCAPE",
            "notes": "grounded",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    saved = api_session.scalar(
        select(BriefItemReview).where(BriefItemReview.session_id == review.id)
    )
    assert saved is not None
    assert saved.evidence_set_usefulness.value == "ESSENTIAL"
    assert saved.notes == "grounded"


def test_reviewer_can_confirm_no_missing_events(client: TestClient, api_session: Session) -> None:
    brief = seed_brief(api_session)
    client.post(
        f"/internal/briefs/{brief.id}/quality-review/start",
        data={"reviewer": "owner"},
    )
    review = api_session.scalar(
        select(BriefReviewSession).where(BriefReviewSession.brief_id == brief.id)
    )
    assert review is not None

    response = client.post(
        f"/internal/brief-review-sessions/{review.id}/missing-events",
        data={"missing_events_confirmed": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    api_session.refresh(review)
    assert review.missing_events_confirmed is True


def test_quality_list_shows_review_progress_effort_and_exclusion_reason(
    client: TestClient, api_session: Session
) -> None:
    brief = seed_brief(api_session)
    client.post(f"/internal/briefs/{brief.id}/quality-review/start", data={"reviewer": "owner"})
    review = api_session.scalar(
        select(BriefReviewSession).where(BriefReviewSession.brief_id == brief.id)
    )
    assert review is not None
    client.post(
        f"/internal/brief-review-sessions/{review.id}/activity-pulses",
        data={"client_event_id": "list-pulse", "active_seconds": 9},
    )

    response = client.get("/internal/brief-quality")

    assert "Estimated reading" in response.text
    assert "Reviewed items" in response.text
    assert "Active review" in response.text
    assert "9s" in response.text
    assert "LATEST_PUBLISHED_VERSION_UNREVIEWED" in response.text


def test_completed_session_rejects_missing_event_mutation_as_conflict(
    client: TestClient, api_session: Session
) -> None:
    brief = seed_brief(api_session)
    item = api_session.scalar(select(BriefItem).where(BriefItem.brief_id == brief.id))
    assert item is not None
    service = BriefQualityReviewService(api_session)
    review = service.start_session(brief.id, "owner", now=NOW)
    service.upsert_item_review(review.id, item.id, valid_item_review(), now=NOW)
    service.set_missing_events_confirmed(review.id, True)
    service.record_activity_pulse(review.id, "complete", 10, now=NOW)
    service.complete_session(review.id, now=NOW)
    api_session.commit()

    response = client.post(
        f"/internal/brief-review-sessions/{review.id}/missing-events",
        data={"missing_events_confirmed": "false"},
    )

    assert response.status_code == 409
