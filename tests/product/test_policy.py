from dataclasses import replace

from app.models.enums import (
    CategoryAvailability,
    DataMode,
    PublicationPolicyMode,
    ReviewStatus,
    RunKind,
    RunStatus,
)
from app.product.policy import PublicationContext, PublicationPolicyEvaluator


def valid_context() -> PublicationContext:
    return PublicationContext(
        data_mode=DataMode.LIVE,
        run_kind=RunKind.LIVE,
        run_status=RunStatus.SUCCEEDED,
        has_publishable_claims=True,
        category_status=CategoryAvailability.EXPERIMENTAL,
        review_status=ReviewStatus.APPROVED,
        suppressed=False,
        auto_pipeline_result=True,
    )


def test_manual_policy_requires_human_approval() -> None:
    evaluator = PublicationPolicyEvaluator(PublicationPolicyMode.MANUAL_APPROVAL_REQUIRED)

    assert evaluator.evaluate(valid_context()).publish is True
    assert evaluator.evaluate(
        replace(valid_context(), review_status=ReviewStatus.PENDING)
    ).publish is False


def test_shadow_auto_eligible_policy_keeps_manual_publication_gate() -> None:
    evaluator = PublicationPolicyEvaluator(PublicationPolicyMode.AUTO_PUBLISH_ELIGIBLE)

    decision = evaluator.evaluate(
        replace(valid_context(), review_status=ReviewStatus.PENDING)
    )

    assert decision.auto_publish_eligible is True
    assert decision.publish is False


def test_auto_publish_can_publish_without_approval_but_human_rejection_wins() -> None:
    evaluator = PublicationPolicyEvaluator(PublicationPolicyMode.AUTO_PUBLISH)

    pending = evaluator.evaluate(replace(valid_context(), review_status=ReviewStatus.PENDING))
    rejected = evaluator.evaluate(replace(valid_context(), review_status=ReviewStatus.REJECTED))

    assert pending.publish is True
    assert rejected.publish is False


def test_every_base_gate_is_required() -> None:
    evaluator = PublicationPolicyEvaluator(PublicationPolicyMode.AUTO_PUBLISH)
    invalid = (
        replace(valid_context(), data_mode=DataMode.DEMO),
        replace(valid_context(), run_kind=RunKind.REPLAY),
        replace(valid_context(), run_status=RunStatus.FAILED),
        replace(valid_context(), has_publishable_claims=False),
        replace(valid_context(), category_status=CategoryAvailability.DISABLED),
        replace(valid_context(), suppressed=True),
        replace(valid_context(), auto_pipeline_result=False),
    )

    assert all(not evaluator.evaluate(context).publish for context in invalid)
