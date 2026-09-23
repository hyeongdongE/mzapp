from __future__ import annotations

from sqlalchemy import delete, select

from app.intelligence.facts import FactBuilder, FactValidator
from app.models.enums import Source
from app.models.tables import EventClusterItem, EventEvidence, EventFactEvidence
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


def test_late_evidence_enriches_facts_without_rewriting_existing_fact(db_session) -> None:
    event = seed_event(
        db_session,
        [EvidenceSpec(Source.GITHUB_RELEASES, "Agent SDK v2.0 released")],
        suffix="late-primary",
    )
    original = FactBuilder(db_session).build(event.id)
    original_ids = {fact.id for fact in original}
    late = seed_event(
        db_session,
        [EvidenceSpec(Source.OFFICIAL_AWS, "AWS supports Agent SDK v2.0")],
        suffix="late-secondary",
    )
    for row in db_session.scalars(
        select(EventClusterItem).where(EventClusterItem.event_cluster_id == late.id)
    ):
        row.event_cluster_id = event.id
    for row in db_session.scalars(
        select(EventEvidence).where(EventEvidence.event_cluster_id == late.id)
    ):
        row.event_cluster_id = event.id
    db_session.flush()

    enriched = FactBuilder(db_session).build(event.id)

    assert original_ids <= {fact.id for fact in enriched}
    assert any(fact.text == "AWS supports Agent SDK v2.0" for fact in enriched)
