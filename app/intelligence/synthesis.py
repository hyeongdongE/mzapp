from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.facts import FactValidator, ValidatedFact
from app.models.tables import EventFact


@dataclass(frozen=True)
class BriefDraftContent:
    headline: str
    what_happened: str
    why_it_matters: str
    fact: tuple[str, ...]
    interpretation: str
    watch: str
    fact_ids: tuple[int, ...]


class EvidenceOnlySynthesizer:
    def __init__(self, session: Session) -> None:
        self._session = session

    def synthesize(self, event_id: int) -> BriefDraftContent:
        validator = FactValidator(self._session)
        facts = [
            validator.validate(fact.id)
            for fact in self._session.scalars(
                select(EventFact)
                .where(EventFact.event_cluster_id == event_id)
                .order_by(EventFact.id)
            )
        ]
        publishable = [fact for fact in facts if fact.publishable and fact.evidence_ids]
        if not publishable:
            raise ValueError("event has no publishable supported facts")
        titles = [fact for fact in publishable if fact.kind == "TITLE"]
        if not titles:
            raise ValueError("event has no publishable supported facts")
        headline = titles[0].text
        fact_lines = tuple(_fact_line(fact) for fact in publishable)
        return BriefDraftContent(
            headline=headline,
            what_happened=f"확인된 변화: {headline}",
            why_it_matters="중요도 판단은 확인된 변화의 영향 범위와 후속 조치를 기준으로 합니다.",
            fact=fact_lines,
            interpretation="해석: 확인된 사실의 영향 범위는 후속 자료를 통해 판단해야 합니다.",
            watch="관찰: 공식 후속 발표와 실제 적용 범위를 확인하세요.",
            fact_ids=tuple(fact.id for fact in publishable),
        )


def _fact_line(fact: ValidatedFact) -> str:
    label = {
        "TITLE": "제목",
        "PUBLISHER": "출처",
        "PUBLICATION_DATE": "발행일",
        "RELEASE_TAG": "버전",
        "REPOSITORY": "저장소",
    }.get(fact.kind, fact.kind)
    return f"{label}: {fact.text}"
