from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import EventEvidence, EventFact, EventFactEvidence, RawItem

VALIDATOR_VERSION = "fact-validator-v1"


@dataclass(frozen=True)
class ValidatedFact:
    id: int
    kind: str
    text: str
    structured_value: dict[str, Any]
    publishable: bool
    evidence_ids: tuple[int, ...]


class FactBuilder:
    def __init__(self, session: Session) -> None:
        self._session = session

    def build(self, event_id: int) -> list[ValidatedFact]:
        existing = list(
            self._session.scalars(
                select(EventFact)
                .where(EventFact.event_cluster_id == event_id)
                .order_by(EventFact.id)
            )
        )
        existing_by_key = {(fact.kind, fact.text): fact for fact in existing}
        existing_links = set(
            self._session.execute(
                select(
                    EventFactEvidence.event_fact_id,
                    EventFactEvidence.event_evidence_id,
                ).join(EventFact, EventFact.id == EventFactEvidence.event_fact_id)
                .where(EventFact.event_cluster_id == event_id)
            ).all()
        )

        rows = self._session.execute(
            select(EventEvidence, RawItem)
            .join(RawItem, RawItem.id == EventEvidence.raw_item_id)
            .where(EventEvidence.event_cluster_id == event_id)
            .order_by(EventEvidence.id)
        ).all()
        candidates: dict[tuple[str, str], tuple[dict[str, Any], list[EventEvidence]]] = {}
        for evidence, raw_item in rows:
            if not evidence.publishable:
                continue
            for kind, text, value in _allowed_facts(evidence, raw_item):
                key = (kind, text)
                if key not in candidates:
                    candidates[key] = (value, [])
                candidates[key][1].append(evidence)

        for (kind, text), (structured_value, evidence_rows) in candidates.items():
            fact = existing_by_key.get((kind, text))
            if fact is None:
                fact = EventFact(
                    event_cluster_id=event_id,
                    kind=kind,
                    text=text,
                    structured_value=structured_value,
                    publishable=True,
                    validator_version=VALIDATOR_VERSION,
                )
                self._session.add(fact)
                self._session.flush()
                existing_by_key[(kind, text)] = fact
            for evidence in evidence_rows:
                if (fact.id, evidence.id) in existing_links:
                    continue
                self._session.add(
                    EventFactEvidence(
                        event_fact_id=fact.id,
                        event_evidence_id=evidence.id,
                        support_type="DIRECT",
                        source_field=_source_field(kind),
                        validation_result="SUPPORTED",
                        validator_version=VALIDATOR_VERSION,
                    )
                )
                existing_links.add((fact.id, evidence.id))
        self._session.flush()
        validator = FactValidator(self._session)
        facts = list(
            self._session.scalars(
                select(EventFact)
                .where(EventFact.event_cluster_id == event_id)
                .order_by(EventFact.id)
            )
        )
        return [validator.validate(fact.id) for fact in facts]


class FactValidator:
    def __init__(self, session: Session) -> None:
        self._session = session

    def validate(self, fact_id: int) -> ValidatedFact:
        fact = self._session.get(EventFact, fact_id)
        if fact is None:
            raise ValueError("fact does not exist")
        evidence_ids = tuple(
            self._session.scalars(
                select(EventFactEvidence.event_evidence_id)
                .join(
                    EventEvidence,
                    EventEvidence.id == EventFactEvidence.event_evidence_id,
                )
                .where(
                    EventFactEvidence.event_fact_id == fact_id,
                    EventFactEvidence.validation_result == "SUPPORTED",
                    EventEvidence.publishable.is_(True),
                )
                .order_by(EventFactEvidence.event_evidence_id)
            )
        )
        fact.publishable = bool(evidence_ids)
        fact.validator_version = VALIDATOR_VERSION
        self._session.flush()
        return ValidatedFact(
            id=fact.id,
            kind=fact.kind,
            text=fact.text,
            structured_value=fact.structured_value,
            publishable=fact.publishable,
            evidence_ids=evidence_ids,
        )


def _allowed_facts(
    evidence: EventEvidence, raw_item: RawItem
) -> list[tuple[str, str, dict[str, Any]]]:
    facts = [
        ("TITLE", raw_item.title, {"title": raw_item.title}),
        (
            "PUBLISHER",
            str(evidence.fact["attribution"]),
            {"publisher": evidence.fact["attribution"]},
        ),
        (
            "PUBLICATION_DATE",
            raw_item.published_at.date().isoformat(),
            {"published_at": raw_item.published_at.isoformat()},
        ),
    ]
    release_tag = raw_item.item_metadata.get("release_tag")
    if isinstance(release_tag, str) and release_tag:
        facts.append(("RELEASE_TAG", release_tag, {"release_tag": release_tag}))
    repository = raw_item.item_metadata.get("repository")
    if isinstance(repository, str) and repository:
        facts.append(("REPOSITORY", repository, {"repository": repository}))
    return facts


def _source_field(kind: str) -> str:
    return {
        "TITLE": "title",
        "PUBLISHER": "attribution",
        "PUBLICATION_DATE": "published_at",
        "RELEASE_TAG": "metadata.release_tag",
        "REPOSITORY": "metadata.repository",
    }[kind]
