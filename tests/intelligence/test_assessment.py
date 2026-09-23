from __future__ import annotations

from app.intelligence.assessment import AssessmentService
from app.models.enums import ClusterStatus, EvidenceConfidence, Source
from tests.intelligence.helpers import EvidenceSpec, seed_event


def test_confidence_and_importance_are_independent_components(db_session) -> None:
    quiet_official = seed_event(
        db_session,
        [
            EvidenceSpec(Source.OFFICIAL_AWS, "Documentation maintenance update"),
            EvidenceSpec(Source.GITHUB_RELEASES, "Documentation maintenance update"),
        ],
        suffix="quiet-official",
    )
    interesting_rumor = seed_event(
        db_session,
        [EvidenceSpec(Source.HACKER_NEWS, "Critical AI model launch rumor")],
        suffix="interesting-rumor",
    )
    service = AssessmentService(db_session)

    quiet = service.assess(quiet_official.id, version="assessment-v1")
    rumor = service.assess(interesting_rumor.id, version="assessment-v1")

    assert quiet.confidence in {EvidenceConfidence.SUPPORTED, EvidenceConfidence.STRONG}
    assert quiet.importance < rumor.importance
    assert rumor.confidence is EvidenceConfidence.LOW
    assert "importance" not in quiet.confidence_breakdown
    assert "confidence" not in quiet.importance_breakdown


def test_source_changes_do_not_change_importance_components(db_session) -> None:
    title = "Critical container security fix released"
    community = seed_event(
        db_session,
        [EvidenceSpec(Source.HACKER_NEWS, title)],
        suffix="community-security",
    )
    official = seed_event(
        db_session,
        [
            EvidenceSpec(Source.OFFICIAL_AWS, title),
            EvidenceSpec(Source.GITHUB_RELEASES, title),
        ],
        suffix="official-security",
    )
    service = AssessmentService(db_session)

    left = service.assess(community.id, version="assessment-v1")
    right = service.assess(official.id, version="assessment-v1")

    assert left.importance_breakdown == right.importance_breakdown
    assert left.confidence != right.confidence


def test_title_changes_do_not_change_confidence_components(db_session) -> None:
    low = seed_event(
        db_session,
        [EvidenceSpec(Source.OFFICIAL_AWS, "Documentation wording update")],
        suffix="low-importance",
    )
    high = seed_event(
        db_session,
        [EvidenceSpec(Source.OFFICIAL_AWS, "Critical security outage")],
        suffix="high-importance",
    )
    service = AssessmentService(db_session)

    left = service.assess(low.id, version="assessment-v1")
    right = service.assess(high.id, version="assessment-v1")

    assert left.confidence_breakdown == right.confidence_breakdown
    assert left.importance != right.importance


def test_syndication_and_ambiguity_reduce_confidence(db_session) -> None:
    duplicate_url = "https://vendor.example/one-event"
    syndicated = seed_event(
        db_session,
        [
            EvidenceSpec(Source.GEEKNEWS, "One event", duplicate_url),
            EvidenceSpec(Source.HACKER_NEWS, "One event", duplicate_url),
        ],
        suffix="syndicated",
    )
    ambiguous = seed_event(
        db_session,
        [EvidenceSpec(Source.OFFICIAL_AWS, "Potential platform update")],
        status=ClusterStatus.NEEDS_REVIEW,
        suffix="ambiguous",
    )
    service = AssessmentService(db_session)

    syndicated_result = service.assess(syndicated.id, version="assessment-v1")
    ambiguous_result = service.assess(ambiguous.id, version="assessment-v1")

    assert syndicated_result.confidence is EvidenceConfidence.LOW
    assert syndicated_result.confidence_breakdown["syndication_penalty"] > 0
    assert ambiguous_result.confidence_breakdown["ambiguity_penalty"] > 0
