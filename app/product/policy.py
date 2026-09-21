from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import (
    CategoryAvailability,
    DataMode,
    PublicationPolicyMode,
    ReviewStatus,
    RunKind,
    RunStatus,
)


@dataclass(frozen=True)
class PublicationContext:
    data_mode: DataMode
    run_kind: RunKind
    run_status: RunStatus
    has_publishable_claims: bool
    category_status: CategoryAvailability
    review_status: ReviewStatus
    suppressed: bool
    auto_pipeline_result: bool


@dataclass(frozen=True)
class PublicationDecision:
    publish: bool
    auto_publish_eligible: bool
    reason: str


class PublicationPolicyEvaluator:
    def __init__(self, mode: PublicationPolicyMode) -> None:
        self._mode = mode

    def evaluate(self, context: PublicationContext) -> PublicationDecision:
        base_checks = (
            context.data_mode is DataMode.LIVE,
            context.run_kind is RunKind.LIVE,
            context.run_status is RunStatus.SUCCEEDED,
            context.has_publishable_claims,
            context.category_status
            in (CategoryAvailability.EXPERIMENTAL, CategoryAvailability.ENABLED),
            not context.suppressed,
            context.auto_pipeline_result,
        )
        if not all(base_checks):
            return PublicationDecision(False, False, "BASE_GATE_FAILED")
        if context.review_status in (ReviewStatus.REJECTED, ReviewStatus.NOISE):
            return PublicationDecision(False, False, "HUMAN_REJECTED")

        auto_eligible = self._mode in (
            PublicationPolicyMode.AUTO_PUBLISH_ELIGIBLE,
            PublicationPolicyMode.AUTO_PUBLISH,
        )
        if self._mode is PublicationPolicyMode.AUTO_PUBLISH:
            return PublicationDecision(True, True, "AUTO_PUBLISH")
        approved = context.review_status is ReviewStatus.APPROVED
        return PublicationDecision(
            approved,
            auto_eligible,
            "HUMAN_APPROVED" if approved else "MANUAL_APPROVAL_REQUIRED",
        )
