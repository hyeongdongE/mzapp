from __future__ import annotations

from sqlalchemy import delete, select

from app.intelligence.facts import FactBuilder, FactValidator
from app.models.enums import Source
from app.models.tables import EventFactEvidence
from tests.intelligence.helpers import EvidenceSpec, seed_event


def test_every_publishable_fact_has_exact_supporting_evidence(db_session) -> None:
    event = seed_event(
        db_session,
        [
            EvidenceSpec(
                Source.GITHUB_RELEASES,
                "Claude Code v2.1.0 released",
                metadata={"repository": "anthropics/claude-code", "release_tag": "v2.1.0"},
            ),
            EvidenceSpec(Source.OFFICIAL_AWS, "AWS adds Claude Code v2.1.0 support"),
        ],
    )

    facts = FactBuilder(db_session).build(event.id)

    assert facts
    assert all(fact.publishable and fact.evidence_ids for fact in facts)
    assert any(fact.kind == "RELEASE_TAG" for fact in facts)
    assert any(fact.kind == "REPOSITORY" for fact in facts)


def test_fact_with_missing_evidence_is_not_publishable(db_session) -> None:
    event = seed_event(
        db_session,
        [EvidenceSpec(Source.OFFICIAL_CLOUDFLARE, "Workers runtime release")],
        suffix="missing-evidence",
    )
    fact = FactBuilder(db_session).build(event.id)[0]
    db_session.execute(
        delete(EventFactEvidence).where(EventFactEvidence.event_fact_id == fact.id)
    )
    db_session.flush()

    assert FactValidator(db_session).validate(fact.id).publishable is False


def test_geeknews_private_summary_never_enters_fact_text(db_session) -> None:
    event = seed_event(
        db_session,
        [
            EvidenceSpec(
                Source.GEEKNEWS,
                "Public title",
                metadata={"private_summary": "do not redistribute this summary"},
            )
        ],
        suffix="geeknews-policy",
    )

    facts = FactBuilder(db_session).build(event.id)

    assert all("do not redistribute" not in fact.text for fact in facts)
    assert db_session.scalars(select(EventFactEvidence)).all()
