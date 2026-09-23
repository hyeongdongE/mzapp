from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    BriefItemUsefulness,
    BriefReviewSessionStatus,
    BriefStatus,
    DuplicateEscapeVerdict,
    EventSelectionVerdict,
    EvidenceSetUsefulness,
    FactCorrectness,
    IncorrectMergeVerdict,
    InterpretationQuality,
    MissingEventDiscoverySource,
    VerbosityVerdict,
    WatchUsefulness,
)
from app.models.tables import (
    BriefItem,
    BriefItemReview,
    BriefItemReviewMergeMembership,
    BriefReviewActivityPulse,
    BriefReviewReopen,
    BriefReviewSession,
    DailyBrief,
    EventCluster,
    EventClusterItem,
    MissingEventReview,
)


class ReviewConflict(ValueError):
    """The requested write conflicts with review state or ownership."""


@dataclass(frozen=True)
class ItemReviewInput:
    usefulness: BriefItemUsefulness
    event_selection: EventSelectionVerdict
    fact_correctness: FactCorrectness
    interpretation_quality: InterpretationQuality
    watch_usefulness: WatchUsefulness
    verbosity: VerbosityVerdict
    evidence_set_usefulness: EvidenceSetUsefulness
    incorrect_merge_verdict: IncorrectMergeVerdict
    duplicate_escape_verdict: DuplicateEscapeVerdict
    duplicate_of_brief_item_id: int | None = None
    duplicate_of_event_cluster_id: int | None = None
    incorrect_merge_membership_ids: tuple[int, ...] = ()
    notes: str | None = None


@dataclass(frozen=True)
class MissingEventInput:
    canonical_title: str
    canonical_url: str
    discovered_from: MissingEventDiscoverySource
    reason: str


class BriefQualityReviewService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def start_session(
        self, brief_id: int, reviewer: str, *, now: datetime
    ) -> BriefReviewSession:
        reviewer = reviewer.strip()
        if not reviewer:
            raise ValueError("reviewer is required")
        brief = self._session.get(DailyBrief, brief_id)
        if brief is None:
            raise LookupError("brief not found")
        if brief.status is not BriefStatus.PUBLISHED:
            raise ReviewConflict("only PUBLISHED briefs can be reviewed")
        existing = self._session.scalar(
            select(BriefReviewSession).where(
                BriefReviewSession.brief_id == brief_id,
                BriefReviewSession.reviewer == reviewer,
            )
        )
        if existing is not None:
            return existing
        review = BriefReviewSession(
            brief_id=brief_id,
            reviewer=reviewer,
            status=BriefReviewSessionStatus.OPEN,
            started_at=now,
        )
        self._session.add(review)
        self._session.flush()
        return review

    def record_activity_pulse(
        self,
        session_id: int,
        client_event_id: str,
        active_seconds: int,
        *,
        now: datetime,
    ) -> bool:
        if not 1 <= active_seconds <= 30:
            raise ValueError("active_seconds must be 1 through 30")
        client_event_id = client_event_id.strip()
        if not client_event_id:
            raise ValueError("client_event_id is required")
        self._locked_open_session(session_id)
        existing = self._session.scalar(
            select(BriefReviewActivityPulse.id).where(
                BriefReviewActivityPulse.session_id == session_id,
                BriefReviewActivityPulse.client_event_id == client_event_id,
            )
        )
        if existing is not None:
            return False
        self._session.add(
            BriefReviewActivityPulse(
                session_id=session_id,
                client_event_id=client_event_id,
                active_seconds=active_seconds,
                recorded_at=now,
            )
        )
        self._session.flush()
        return True

    def active_review_seconds(self, session_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.coalesce(func.sum(BriefReviewActivityPulse.active_seconds), 0)).where(
                    BriefReviewActivityPulse.session_id == session_id
                )
            )
            or 0
        )

    def set_missing_events_confirmed(self, session_id: int, confirmed: bool) -> None:
        review = self._locked_open_session(session_id)
        review.missing_events_confirmed = confirmed
        self._session.flush()

    def update_overall_notes(self, session_id: int, notes: str | None) -> None:
        review = self._locked_open_session(session_id)
        review.overall_notes = _optional_text(notes)
        self._session.flush()

    def upsert_item_review(
        self,
        session_id: int,
        brief_item_id: int,
        data: ItemReviewInput,
        *,
        now: datetime,
    ) -> BriefItemReview:
        review_session = self._locked_open_session(session_id)
        item = self._session.get(BriefItem, brief_item_id)
        if item is None or item.brief_id != review_session.brief_id:
            raise ReviewConflict("BriefItem does not belong to the review Brief")
        self._validate_duplicate_target(item, data)
        memberships = self._validated_memberships(item, data)
        review = self._session.scalar(
            select(BriefItemReview).where(
                BriefItemReview.session_id == session_id,
                BriefItemReview.brief_item_id == brief_item_id,
            )
        )
        values = {
            "usefulness": data.usefulness,
            "event_selection": data.event_selection,
            "fact_correctness": data.fact_correctness,
            "interpretation_quality": data.interpretation_quality,
            "watch_usefulness": data.watch_usefulness,
            "verbosity": data.verbosity,
            "evidence_set_usefulness": data.evidence_set_usefulness,
            "incorrect_merge_verdict": data.incorrect_merge_verdict,
            "duplicate_escape_verdict": data.duplicate_escape_verdict,
            "duplicate_of_brief_item_id": data.duplicate_of_brief_item_id,
            "duplicate_of_event_cluster_id": data.duplicate_of_event_cluster_id,
            "notes": _optional_text(data.notes),
            "updated_at": now,
        }
        if review is None:
            review = BriefItemReview(
                session_id=session_id, brief_item_id=brief_item_id, created_at=now, **values
            )
            self._session.add(review)
            self._session.flush()
        else:
            for name, value in values.items():
                setattr(review, name, value)
        self._session.execute(
            delete(BriefItemReviewMergeMembership).where(
                BriefItemReviewMergeMembership.brief_item_review_id == review.id
            )
        )
        for membership in memberships:
            self._session.add(
                BriefItemReviewMergeMembership(
                    brief_item_review_id=review.id,
                    event_cluster_item_id=membership.id,
                )
            )
        self._session.flush()
        return review

    def add_missing_event(
        self, session_id: int, data: MissingEventInput, *, now: datetime
    ) -> MissingEventReview:
        self._locked_open_session(session_id)
        title = data.canonical_title.strip()
        reason = data.reason.strip()
        if not title or not reason:
            raise ValueError("missing event title and reason are required")
        canonical_url = _canonical_https_url(data.canonical_url)
        existing = self._session.scalar(
            select(MissingEventReview).where(
                MissingEventReview.session_id == session_id,
                MissingEventReview.canonical_url == canonical_url,
            )
        )
        if existing is None:
            existing = MissingEventReview(
                session_id=session_id,
                canonical_title=title,
                canonical_url=canonical_url,
                discovered_from=data.discovered_from,
                reason=reason,
                created_at=now,
                updated_at=now,
            )
            self._session.add(existing)
        else:
            existing.canonical_title = title
            existing.discovered_from = data.discovered_from
            existing.reason = reason
            existing.updated_at = now
        self._session.flush()
        return existing

    def delete_missing_event(self, session_id: int, missing_event_id: int) -> None:
        self._locked_open_session(session_id)
        event = self._session.get(MissingEventReview, missing_event_id)
        if event is None or event.session_id != session_id:
            raise ReviewConflict("missing event does not belong to session")
        self._session.delete(event)
        self._session.flush()

    def complete_session(self, session_id: int, *, now: datetime) -> BriefReviewSession:
        review = self._locked_open_session(session_id)
        item_count = int(
            self._session.scalar(
                select(func.count()).select_from(BriefItem).where(
                    BriefItem.brief_id == review.brief_id
                )
            )
            or 0
        )
        reviewed_count = int(
            self._session.scalar(
                select(func.count()).select_from(BriefItemReview).where(
                    BriefItemReview.session_id == session_id
                )
            )
            or 0
        )
        if item_count == 0 or reviewed_count != item_count:
            raise ReviewConflict("a complete item review is required for every BriefItem")
        if not review.missing_events_confirmed:
            raise ReviewConflict("missing events must be explicitly confirmed")
        if self.active_review_seconds(session_id) <= 0:
            raise ReviewConflict("active review time is required")
        review.status = BriefReviewSessionStatus.COMPLETED
        review.completed_at = now
        review.completion_revision += 1
        self._session.flush()
        return review

    def reopen_session(
        self, session_id: int, *, actor: str, reason: str, now: datetime
    ) -> BriefReviewSession:
        review = self._locked_session(session_id)
        actor = actor.strip()
        reason = reason.strip()
        if not actor or not reason:
            raise ValueError("reopen actor and reason are required")
        if review.status is not BriefReviewSessionStatus.COMPLETED or review.completed_at is None:
            raise ReviewConflict("only a completed session can be reopened")
        self._session.add(
            BriefReviewReopen(
                session_id=session_id,
                actor=actor,
                reason=reason,
                reopened_at=now,
                previous_completed_at=review.completed_at,
                previous_completion_revision=review.completion_revision,
            )
        )
        review.status = BriefReviewSessionStatus.OPEN
        review.completed_at = None
        self._session.flush()
        return review

    def _locked_session(self, session_id: int) -> BriefReviewSession:
        review = self._session.scalar(
            select(BriefReviewSession)
            .where(BriefReviewSession.id == session_id)
            .with_for_update()
        )
        if review is None:
            raise LookupError("review session not found")
        return review

    def _locked_open_session(self, session_id: int) -> BriefReviewSession:
        review = self._locked_session(session_id)
        if review.status is BriefReviewSessionStatus.COMPLETED:
            raise ReviewConflict("completed sessions are immutable; reopen first")
        return review

    def _validate_duplicate_target(self, item: BriefItem, data: ItemReviewInput) -> None:
        has_target = (
            data.duplicate_of_brief_item_id is not None
            or data.duplicate_of_event_cluster_id is not None
        )
        if data.duplicate_escape_verdict is DuplicateEscapeVerdict.DUPLICATE_ESCAPE:
            if not has_target:
                raise ReviewConflict("duplicate escape requires a structured target")
        elif has_target:
            raise ReviewConflict("duplicate target requires DUPLICATE_ESCAPE verdict")
        if data.duplicate_of_brief_item_id is not None:
            target = self._session.get(BriefItem, data.duplicate_of_brief_item_id)
            if target is None or target.brief_id != item.brief_id or target.id == item.id:
                raise ReviewConflict("duplicate BriefItem target must be another item in the Brief")
        if (
            data.duplicate_of_event_cluster_id is not None
            and self._session.get(EventCluster, data.duplicate_of_event_cluster_id) is None
        ):
            raise ReviewConflict("duplicate EventCluster target does not exist")

    def _validated_memberships(
        self, item: BriefItem, data: ItemReviewInput
    ) -> list[EventClusterItem]:
        ids = tuple(dict.fromkeys(data.incorrect_merge_membership_ids))
        if data.incorrect_merge_verdict is IncorrectMergeVerdict.INCORRECT_MERGE:
            if not ids:
                raise ReviewConflict("incorrect merge requires at least one cluster membership")
        elif ids:
            raise ReviewConflict("merge memberships require INCORRECT_MERGE verdict")
        memberships = [self._session.get(EventClusterItem, item_id) for item_id in ids]
        if any(
            value is None or value.event_cluster_id != item.event_cluster_id
            for value in memberships
        ):
            raise ReviewConflict("merge membership must belong to the BriefItem EventCluster")
        return [value for value in memberships if value is not None]


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _canonical_https_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError("canonical_url must be an HTTPS URL")
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))
