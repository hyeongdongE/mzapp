from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ai.contracts import (
    UNKNOWN_CAUSE_MESSAGE,
    ClaimDraft,
    ClaimKind,
    EvidenceRecord,
    interest_claim_text,
)
from app.ai.evidence import EvidenceChecker
from app.models.enums import EvidenceStatus, Source

AS_OF = datetime(2026, 9, 20, 12, tzinfo=UTC)


def evidence(
    evidence_id: int,
    *,
    entity_id: int = 1,
    kind: str = "TREND_SIGNAL",
    observed_at: datetime = AS_OF,
) -> EvidenceRecord:
    return EvidenceRecord(
        id=evidence_id,
        entity_id=entity_id,
        observation_id=evidence_id,
        source=Source.GOOGLE_TRENDS,
        kind=kind,
        fact={
            "canonical_text": "테스트 주제",
            "metrics": {"traffic": 100},
            "source_timestamp": AS_OF.isoformat(),
        },
        source_url="https://trends.google.com/trending/rss?geo=KR",
        observed_at=observed_at,
    )


def test_unsupported_claim_is_not_publishable() -> None:
    claim = ClaimDraft(
        kind=ClaimKind.CAUSE,
        text="새 제품 출시로 검색이 늘었습니다.",
        evidence_ids=[],
    )

    checked = EvidenceChecker().check(
        claim, [], entity_id=1, entity_name="테스트 주제", as_of=AS_OF
    )

    assert checked.status is EvidenceStatus.UNSUPPORTED
    assert checked.publishable is False


def test_nonexistent_future_and_wrong_entity_evidence_are_rejected() -> None:
    checker = EvidenceChecker()
    available = [
        evidence(1),
        evidence(2, observed_at=AS_OF + timedelta(seconds=1)),
        evidence(3, entity_id=2),
    ]

    assert checker.check(
        ClaimDraft(kind=ClaimKind.INTEREST, text="관심 증가", evidence_ids=[99]),
        available,
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    ).status is EvidenceStatus.UNSUPPORTED
    assert checker.check(
        ClaimDraft(kind=ClaimKind.INTEREST, text="관심 증가", evidence_ids=[2]),
        available,
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    ).reason == "FUTURE_EVIDENCE"
    assert checker.check(
        ClaimDraft(kind=ClaimKind.INTEREST, text="관심 증가", evidence_ids=[3]),
        available,
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    ).reason == "ENTITY_MISMATCH"


def test_unapproved_url_and_future_source_timestamp_are_rejected() -> None:
    checker = EvidenceChecker()
    unapproved = evidence(1).model_copy(update={"source_url": "https://evil.test/data"})
    future_source = evidence(2).model_copy(
        update={
            "fact": {
                **evidence(2).fact,
                "source_timestamp": "2026-09-20T12:00:01+00:00",
            }
        }
    )

    assert checker.check(
        ClaimDraft(kind=ClaimKind.INTEREST, text="관심 증가", evidence_ids=[1]),
        [unapproved],
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    ).reason == "UNAPPROVED_SOURCE_URL"
    assert checker.check(
        ClaimDraft(kind=ClaimKind.INTEREST, text="관심 증가", evidence_ids=[2]),
        [future_source],
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    ).reason == "FUTURE_SOURCE_TIMESTAMP"


def test_interest_signal_cannot_support_a_causal_claim() -> None:
    checked = EvidenceChecker().check(
        ClaimDraft(kind=ClaimKind.CAUSE, text="행사 때문에 증가", evidence_ids=[1]),
        [evidence(1)],
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    )

    assert checked.status is EvidenceStatus.UNSUPPORTED
    assert checked.reason == "CAUSAL_EVIDENCE_REQUIRED"
    assert checked.publishable is False


def test_fixed_unknown_cause_message_is_publishable_without_causal_evidence() -> None:
    checked = EvidenceChecker().check(
        ClaimDraft(kind=ClaimKind.CAUSE, text=UNKNOWN_CAUSE_MESSAGE, evidence_ids=[1]),
        [evidence(1)],
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    )

    assert checked.status is EvidenceStatus.SUPPORTED
    assert checked.reason == "NO_CAUSAL_EVIDENCE_AVAILABLE"
    assert checked.publishable is True


def test_claim_kind_must_match_trusted_evidence_kind() -> None:
    checker = EvidenceChecker()

    interest = checker.check(
        ClaimDraft(
            kind=ClaimKind.INTEREST,
            text=interest_claim_text("테스트 주제", {Source.GOOGLE_TRENDS}),
            evidence_ids=[1],
        ),
        [evidence(1)],
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    )
    wikidata = evidence(2, kind="WIKIDATA_ENTITY").model_copy(
        update={
            "observation_id": None,
            "resolution_attempt_id": 1,
            "raw_fetch_id": 1,
            "source": Source.WIKIDATA,
            "source_url": "https://www.wikidata.org/wiki/Q1",
            "fact": {
                "wikidata_id": "Q1",
                "canonical_name": "테스트 주제",
                "description": "대상 설명",
                "entity_types": [],
            },
        }
    )
    what = checker.check(
        ClaimDraft(kind=ClaimKind.WHAT, text="테스트 주제: 대상 설명", evidence_ids=[2]),
        [wikidata],
        entity_id=1,
        entity_name="테스트 주제",
        entity_wikidata_id="Q1",
        as_of=AS_OF,
    )

    assert interest.status is EvidenceStatus.SUPPORTED
    assert interest.publishable is True
    assert what.status is EvidenceStatus.SUPPORTED
    assert what.publishable is True


def test_claim_text_must_match_the_evidence_fact() -> None:
    causal = evidence(1, kind="CAUSAL_EVENT").model_copy(
        update={
            "fact": {
                **evidence(1).fact,
                "cause": "공식 행사가 시작되었습니다.",
                "trusted_parser": True,
            }
        }
    )

    checked = EvidenceChecker().check(
        ClaimDraft(kind=ClaimKind.CAUSE, text="제품 출시 때문입니다.", evidence_ids=[1]),
        [causal],
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    )

    assert checked.status is EvidenceStatus.UNSUPPORTED
    assert checked.reason == "CLAIM_EVIDENCE_MISMATCH"
    assert checked.publishable is False


def test_kind_source_and_required_provenance_must_agree() -> None:
    forged = evidence(1, kind="WIKIDATA_ENTITY").model_copy(
        update={"fact": {"description": "임의 설명", "canonical_name": "테스트 주제"}}
    )

    checked = EvidenceChecker().check(
        ClaimDraft(kind=ClaimKind.WHAT, text="테스트 주제: 임의 설명", evidence_ids=[1]),
        [forged],
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    )

    assert checked.status is EvidenceStatus.UNSUPPORTED
    assert checked.reason == "INVALID_EVIDENCE_PROVENANCE"


def test_non_string_source_timestamp_fails_closed() -> None:
    malformed = evidence(1).model_copy(update={"fact": {"source_timestamp": 42}})

    checked = EvidenceChecker().check(
        ClaimDraft(
            kind=ClaimKind.INTEREST,
            text=interest_claim_text("테스트 주제", {Source.GOOGLE_TRENDS}),
            evidence_ids=[1],
        ),
        [malformed],
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    )

    assert checked.status is EvidenceStatus.UNSUPPORTED
    assert checked.reason == "INVALID_EVIDENCE_PROVENANCE"


def test_unselected_contradiction_blocks_publishable_claim() -> None:
    supporting = evidence(1, kind="CAUSAL_EVENT").model_copy(
        update={
            "fact": {
                **evidence(1).fact,
                "cause": "공식 행사가 시작되었습니다.",
                "trusted_parser": True,
            }
        }
    )
    contradiction = evidence(2, kind="CAUSAL_EVENT").model_copy(
        update={"fact": {"contradicts_claim": True}}
    )

    checked = EvidenceChecker().check(
        ClaimDraft(
            kind=ClaimKind.CAUSE,
            text="공식 행사가 시작되었습니다.",
            evidence_ids=[1],
        ),
        [supporting, contradiction],
        entity_id=1,
        entity_name="테스트 주제",
        as_of=AS_OF,
    )

    assert checked.status is EvidenceStatus.CONTRADICTED
    assert checked.publishable is False
