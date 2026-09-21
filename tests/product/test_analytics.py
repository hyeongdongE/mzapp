from datetime import timedelta

from app.models.enums import (
    DataMode,
    EvidenceStatus,
    FeedbackType,
    HumanEvaluationLabel,
    ReviewAction,
    ReviewStatus,
)
from app.models.tables import (
    AnonymousUser,
    Claim,
    ClaimSnapshot,
    HumanEvaluation,
    ProductTrendCard,
    Review,
    SavedTrend,
    TrendFeedback,
    TrendInteraction,
)
from app.product.analytics import ProductAnalytics
from tests.api.public_fixtures import NOW, authenticate_with_interest, seed_live_card

pytest_plugins = ["tests.api.conftest"]


def test_live_metrics_calculate_discovery_open_save_and_feedback_rates(
    client, api_session
) -> None:
    card = seed_live_card(api_session)
    authenticate_with_interest(client)
    client.post(
        "/api/public/events",
        json={"eventType": "TREND_IMPRESSION", "trendId": card.public_id},
    )
    client.get(f"/api/public/trends/{card.public_id}")
    client.put(
        f"/api/public/trends/{card.public_id}/feedback",
        json={"feedbackType": "NEW_AND_USEFUL"},
    )
    client.put(f"/api/public/trends/{card.public_id}/save")

    metrics = ProductAnalytics(api_session).summary(DataMode.LIVE)

    assert metrics["impressions"] == 1
    assert metrics["opens"] == 1
    assert metrics["discovery_value_rate"] == 1.0
    assert metrics["already_known_rate"] == 0.0
    assert metrics["save_rate"] == 1.0


def test_demo_events_never_enter_live_metrics(api_session) -> None:
    user = AnonymousUser(
        id="demo-user",
        credential_hash="d" * 64,
        data_mode=DataMode.DEMO,
        created_at=NOW,
        last_seen_at=NOW,
    )
    card = ProductTrendCard(
        public_id="demo-card",
        data_mode=DataMode.DEMO,
        fixture_key="demo-card",
        title="DEMO",
        category="FOOD",
        lifecycle="RISING",
        what_text="demo",
        interest_text="demo",
        sources=[],
        first_seen_at=NOW,
        observed_at=NOW,
        trend_score=1,
        auto_pipeline_result=True,
        suppressed=False,
        created_at=NOW,
        updated_at=NOW,
    )
    api_session.add_all([user, card])
    api_session.flush()
    api_session.add_all(
        [
            TrendInteraction(
                user_id=user.id,
                card_id=card.id,
                first_impression_at=NOW,
                last_impression_at=NOW,
                impression_count=20,
                open_count=10,
            ),
            TrendFeedback(
                user_id=user.id,
                card_id=card.id,
                feedback_type=FeedbackType.NEW_AND_USEFUL,
                created_at=NOW,
                updated_at=NOW,
            ),
            SavedTrend(user_id=user.id, card_id=card.id, created_at=NOW),
        ]
    )
    api_session.commit()

    assert ProductAnalytics(api_session).summary(DataMode.LIVE)["impressions"] == 0


def test_return_metrics_use_user_first_and_last_seen_dates(api_session) -> None:
    from app.models.tables import AnonymousUser

    api_session.add(
        AnonymousUser(
            id="returning-user",
            credential_hash="a" * 64,
            data_mode=DataMode.LIVE,
            created_at=NOW,
            last_seen_at=NOW + timedelta(days=7, minutes=1),
        )
    )
    api_session.commit()

    metrics = ProductAnalytics(api_session).summary(DataMode.LIVE)

    assert metrics["d1_return_rate"] == 1.0
    assert metrics["d7_return_rate"] == 1.0


def test_category_performance_contains_auto_publish_decision_inputs(api_session) -> None:
    card = seed_live_card(api_session)
    unsupported = Claim(
        entity_id=card.entity_id,
        kind="CAUSE",
        text="unsupported",
        status=EvidenceStatus.UNSUPPORTED,
        reason="NO_EVIDENCE",
        publishable=False,
        prompt_version="p1",
        evidence_set_hash="z" * 64,
        created_at=NOW,
    )
    api_session.add(unsupported)
    api_session.flush()
    api_session.add_all(
        [
            HumanEvaluation(
                entity_id=card.entity_id,
                label=HumanEvaluationLabel.VALID_TREND,
                actor="reviewer",
                created_at=NOW,
            ),
            ClaimSnapshot(claim_id=unsupported.id, snapshot_id=card.snapshot_id),
            Review(
                entity_id=card.entity_id,
                product_card_id=card.id,
                snapshot_id=card.snapshot_id,
                category_at_review=card.category,
                action=ReviewAction.APPROVE,
                actor="reviewer",
                reason="supported",
                payload={},
                previous_status=ReviewStatus.PENDING,
                resulting_status=ReviewStatus.APPROVED,
                auto_pipeline_result=True,
                created_at=NOW,
            ),
        ]
    )
    api_session.commit()

    row = next(
        item
        for item in ProductAnalytics(api_session).category_performance(now=NOW)
        if item["category"] == "AI_TECH"
    )

    assert row["window_days"] == 14
    assert row["valid_trends_per_day"] == 0.07
    assert row["false_positive_rate"] == 0.0
    assert row["unsupported_claim_rate"] == 0.3333
    assert row["auto_publishable_cards"] == 1
    assert row["shadow_auto_eligible_cards"] == 1
    assert row["human_reviewed_cards"] == 1
    assert row["review_rejection_rate"] == 0.0
    assert row["human_approval_rate"] == 1.0


def test_category_claim_rate_ignores_claims_not_linked_to_live_cards(api_session) -> None:
    card = seed_live_card(api_session)
    api_session.add(
        Claim(
            entity_id=card.entity_id,
            kind="CAUSE",
            text="replay-only unsupported claim",
            status=EvidenceStatus.UNSUPPORTED,
            reason="NO_EVIDENCE",
            publishable=False,
            prompt_version="replay-p1",
            evidence_set_hash="r" * 64,
            created_at=NOW,
        )
    )
    api_session.commit()

    row = next(
        item
        for item in ProductAnalytics(api_session).category_performance(now=NOW)
        if item["category"] == "AI_TECH"
    )

    assert row["unsupported_claim_rate"] == 0.0


def test_category_review_metrics_use_latest_decision_per_card(api_session) -> None:
    card = seed_live_card(api_session)
    api_session.add_all(
        [
            Review(
                entity_id=card.entity_id,
                product_card_id=card.id,
                snapshot_id=card.snapshot_id,
                category_at_review=card.category,
                action=ReviewAction.REJECT,
                actor="reviewer",
                reason="initial rejection",
                payload={},
                previous_status=ReviewStatus.PENDING,
                resulting_status=ReviewStatus.REJECTED,
                auto_pipeline_result=True,
                created_at=NOW - timedelta(minutes=1),
            ),
            Review(
                entity_id=card.entity_id,
                product_card_id=card.id,
                snapshot_id=card.snapshot_id,
                category_at_review=card.category,
                action=ReviewAction.APPROVE,
                actor="reviewer",
                reason="evidence corrected",
                payload={},
                previous_status=ReviewStatus.REJECTED,
                resulting_status=ReviewStatus.APPROVED,
                auto_pipeline_result=True,
                created_at=NOW,
            ),
        ]
    )
    api_session.commit()

    row = next(
        item
        for item in ProductAnalytics(api_session).category_performance(now=NOW)
        if item["category"] == "AI_TECH"
    )

    assert row["human_reviewed_cards"] == 1
    assert row["auto_publishable_reviewed"] == 1
    assert row["human_approval_rate"] == 1.0
    assert row["review_rejection_rate"] == 0.0
