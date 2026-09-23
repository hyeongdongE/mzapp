from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.intelligence.briefs import BriefCandidate, BriefSelector
from app.intelligence.reading_time import ReadingTimeEstimator
from app.intelligence.sources import required_source_keys
from app.intelligence.synthesis import BriefDraftContent, EvidenceOnlySynthesizer
from app.models.enums import BriefStatus, ClusterStatus, EvidenceConfidence
from app.models.tables import (
    BriefItem,
    BriefItemFact,
    DailyBrief,
    EventAssessment,
    EventCluster,
    EventClusterItem,
    EventEvidence,
    EventFact,
    EventFactEvidence,
    RawItem,
    SourceHealth,
)

SEOUL = ZoneInfo("Asia/Seoul")
MIN_IMPORTANCE = 20.0


@dataclass(frozen=True)
class DailyBriefResult:
    brief_id: int
    status: BriefStatus
    item_count: int
    reading_time_seconds: int
    published_at: datetime | None
    version: int


class DailyBriefService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._estimator = ReadingTimeEstimator()
        self._selector = BriefSelector(self._estimator)
        self._synthesizer = EvidenceOnlySynthesizer(session)

    def generate(
        self,
        brief_date: date,
        *,
        now: datetime,
        version: str,
    ) -> DailyBriefResult:
        existing = self._session.scalar(
            select(DailyBrief).where(
                DailyBrief.brief_date == brief_date,
                DailyBrief.generation_version == version,
            )
        )
        if existing is not None:
            return _result(existing)

        window_end = datetime.combine(brief_date, time(7, 30), tzinfo=SEOUL).astimezone(UTC)
        window_start = window_end - timedelta(hours=24)
        next_version = (
            self._session.scalar(
                select(func.max(DailyBrief.version)).where(
                    DailyBrief.brief_date == brief_date
                )
            )
            or 0
        ) + 1
        coverage_ok = self._coverage_is_complete(window_end)
        candidates, drafts = self._candidates(
            brief_date, window_start, window_end, now
        )
        selection = self._selector.select(candidates)

        if not coverage_ok:
            status = BriefStatus.DEGRADED_SOURCE_COVERAGE
            published_at = None
            selected: tuple[BriefCandidate, ...] = ()
        elif selection.rejected:
            status = BriefStatus.REJECTED
            published_at = None
            selected = selection.items
        elif len(selection.items) <= 2:
            status = BriefStatus.LOW_SIGNAL_DAY
            published_at = now
            selected = selection.items
        else:
            status = BriefStatus.PUBLISHED
            published_at = now
            selected = selection.items

        final_text = "\n".join(
            self._rendered_content(
                drafts[item.event_id], compact=selection.used_compact_content
            )
            for item in selected
        )
        reading_seconds = self._estimator.estimate_seconds(final_text)
        brief = DailyBrief(
            brief_date=brief_date,
            version=next_version,
            status=status,
            window_start=window_start,
            window_end=window_end,
            generated_at=now,
            published_at=published_at,
            today_in_one_line=(
                "중요한 IT 변화를 근거와 함께 정리했습니다."
                if selected
                else "오늘은 기준을 충족한 중요한 변화가 없습니다."
            ),
            raw_item_count=self._raw_item_count(window_start, window_end, now),
            event_cluster_count=len(candidates),
            candidate_count=len(candidates),
            selected_count=len(selected),
            word_count=self._estimator.count_units(final_text),
            reading_time_seconds=reading_seconds,
            generation_version=version,
        )
        self._session.add(brief)
        self._session.flush()
        for position, candidate in enumerate(selected, start=1):
            self._persist_item(
                brief.id,
                position,
                candidate,
                drafts[candidate.event_id],
                compact=selection.used_compact_content,
            )
        self._session.flush()
        return _result(brief)

    def _coverage_is_complete(self, window_end: datetime) -> bool:
        for source in required_source_keys():
            health = self._session.get(SourceHealth, source)
            if (
                health is None
                or health.last_success_at is None
                or health.covered_through is None
                or health.freshness_state != "FRESH"
                or health.consecutive_failures != 0
                or _aware_utc(health.covered_through) < window_end
            ):
                return False
        return True

    def _candidates(
        self,
        brief_date: date,
        window_start: datetime,
        window_end: datetime,
        now: datetime,
    ) -> tuple[list[BriefCandidate], dict[int, BriefDraftContent]]:
        already_briefed = set(
            self._session.scalars(
                select(BriefItem.event_cluster_id)
                .join(DailyBrief, DailyBrief.id == BriefItem.brief_id)
                .where(DailyBrief.brief_date < brief_date)
            ).all()
        )
        assessments: dict[int, EventAssessment] = {}
        for assessment in self._session.scalars(
            select(EventAssessment).order_by(EventAssessment.assessed_at, EventAssessment.id)
        ):
            assessments[assessment.event_cluster_id] = assessment
        candidates: list[BriefCandidate] = []
        drafts: dict[int, BriefDraftContent] = {}
        for event_id, assessment in assessments.items():
            if event_id in already_briefed:
                continue
            cluster = self._session.get(EventCluster, event_id)
            if (
                cluster is None
                or cluster.status is not ClusterStatus.ACTIVE
                or _aware_utc(cluster.first_seen_at) > now
                or assessment.confidence
                not in {EvidenceConfidence.SUPPORTED, EvidenceConfidence.STRONG}
                or assessment.importance < MIN_IMPORTANCE
                or not self._has_window_item(event_id, window_start, window_end, now)
            ):
                continue
            try:
                draft = self._synthesizer.synthesize(event_id)
            except ValueError:
                continue
            rendered = self._rendered_content(draft, compact=False)
            compact = self._rendered_content(draft, compact=True)
            candidates.append(
                BriefCandidate(
                    event_id=event_id,
                    confidence=assessment.confidence,
                    importance=assessment.importance,
                    first_seen_at=_aware_utc(cluster.first_seen_at),
                    rendered_text=rendered,
                    compact_text=compact if len(compact) < len(rendered) else None,
                )
            )
            drafts[event_id] = draft
        return candidates, drafts

    def _has_window_item(
        self,
        event_id: int,
        window_start: datetime,
        window_end: datetime,
        now: datetime,
    ) -> bool:
        return (
            self._session.scalar(
                select(RawItem.id)
                .join(EventClusterItem, EventClusterItem.raw_item_id == RawItem.id)
                .where(
                    EventClusterItem.event_cluster_id == event_id,
                    RawItem.published_at >= window_start,
                    RawItem.published_at < window_end,
                    RawItem.collected_at <= now,
                )
                .limit(1)
            )
            is not None
        )

    def _raw_item_count(
        self, window_start: datetime, window_end: datetime, now: datetime
    ) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(RawItem)
                .where(
                    RawItem.published_at >= window_start,
                    RawItem.published_at < window_end,
                    RawItem.collected_at <= now,
                )
            )
            or 0
        )

    def _persist_item(
        self,
        brief_id: int,
        position: int,
        candidate: BriefCandidate,
        draft: BriefDraftContent,
        *,
        compact: bool,
    ) -> None:
        item = BriefItem(
            brief_id=brief_id,
            event_cluster_id=candidate.event_id,
            position=position,
            headline=draft.headline,
            category="IT",
            what_happened=_compact(draft.what_happened) if compact else draft.what_happened,
            why_it_matters=(
                _compact(draft.why_it_matters) if compact else draft.why_it_matters
            ),
            fact_text="\n".join(draft.fact),
            interpretation_text=(
                _compact(draft.interpretation) if compact else draft.interpretation
            ),
            watch_text=_compact(draft.watch) if compact else draft.watch,
            source_links=self._source_links(candidate.event_id),
            importance=candidate.importance,
        )
        self._session.add(item)
        self._session.flush()
        for fact_id in draft.fact_ids:
            fact = self._session.get(EventFact, fact_id)
            if fact is None:
                continue
            evidence_ids = self._session.scalars(
                select(EventFactEvidence.event_evidence_id).where(
                    EventFactEvidence.event_fact_id == fact_id,
                    EventFactEvidence.validation_result == "SUPPORTED",
                )
            )
            for evidence_id in evidence_ids:
                self._session.add(
                    BriefItemFact(
                        brief_item_id=item.id,
                        event_fact_id=fact_id,
                        event_evidence_id=evidence_id,
                        fact_text_snapshot=fact.text,
                    )
                )

    def _source_links(self, event_id: int) -> list[dict[str, str]]:
        evidence = self._session.scalars(
            select(EventEvidence)
            .where(
                EventEvidence.event_cluster_id == event_id,
                EventEvidence.publishable.is_(True),
            )
            .order_by(EventEvidence.id)
        )
        return [
            {
                "url": item.source_url,
                "title": str(item.fact.get("attribution", "Source")),
            }
            for item in evidence
        ]

    def _rendered_content(self, draft: BriefDraftContent, *, compact: bool) -> str:
        values = [
            draft.headline,
            draft.what_happened,
            draft.why_it_matters,
            *draft.fact,
            draft.interpretation,
            draft.watch,
        ]
        if compact:
            values = [values[0], *(_compact(value) for value in values[1:])]
        return "\n".join(values)


def _compact(value: str, limit: int = 180) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _result(brief: DailyBrief) -> DailyBriefResult:
    return DailyBriefResult(
        brief_id=brief.id,
        status=brief.status,
        item_count=brief.selected_count,
        reading_time_seconds=brief.reading_time_seconds,
        published_at=(
            _aware_utc(brief.published_at) if brief.published_at is not None else None
        ),
        version=brief.version,
    )
