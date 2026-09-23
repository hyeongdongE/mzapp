from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.services.test_brief_quality_review import seed_brief


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


def test_non_published_brief_cannot_start_review(
    client: TestClient, api_session: Session
) -> None:
    from app.models.enums import BriefStatus

    brief = seed_brief(api_session, status=BriefStatus.DRAFT)
    response = client.post(
        f"/internal/briefs/{brief.id}/quality-review/start",
        data={"reviewer": "owner"},
    )
    assert response.status_code == 409
