from __future__ import annotations

from app.intelligence.facts import FactBuilder
from app.intelligence.synthesis import EvidenceOnlySynthesizer
from app.models.enums import Source
from tests.intelligence.helpers import EvidenceSpec, seed_event


def test_synthesis_uses_only_validated_facts_and_returns_fact_ids(db_session) -> None:
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
        suffix="synthesis",
    )
    facts = FactBuilder(db_session).build(event.id)

    draft = EvidenceOnlySynthesizer(db_session).synthesize(event.id)

    assert draft.fact_ids == tuple(fact.id for fact in facts)
    assert draft.headline in {fact.text for fact in facts if fact.kind == "TITLE"}
    assert draft.fact
    assert draft.interpretation.startswith("해석:")
    assert draft.watch.startswith("관찰:")
    assert "v2.1.0" in " ".join(draft.fact)


def test_synthesis_rejects_event_without_publishable_supported_facts(db_session) -> None:
    event = seed_event(
        db_session,
        [EvidenceSpec(Source.GEEKNEWS, "Unbuilt event")],
        suffix="no-facts",
    )

    try:
        EvidenceOnlySynthesizer(db_session).synthesize(event.id)
    except ValueError as exc:
        assert str(exc) == "event has no publishable supported facts"
    else:
        raise AssertionError("synthesis must not invent unsupported claims")
