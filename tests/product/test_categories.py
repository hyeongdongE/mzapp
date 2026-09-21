from datetime import UTC, datetime

import pytest

from app.models.enums import Category, CategoryAvailability
from app.models.tables import CategorySetting
from app.product.categories import CategorySettingsService

NOW = datetime(2026, 9, 21, 6, tzinfo=UTC)


def test_operator_can_change_category_status_with_auditable_reason(db_session) -> None:
    db_session.add(
        CategorySetting(
            category=Category.AI_TECH,
            status=CategoryAvailability.DISABLED,
            rationale="insufficient evidence",
            updated_by="migration",
            updated_at=NOW,
        )
    )
    db_session.flush()

    row = CategorySettingsService(db_session).set_status(
        Category.AI_TECH,
        CategoryAvailability.EXPERIMENTAL,
        actor="operator",
        rationale="14-day metrics passed",
        now=NOW,
    )

    assert row.status is CategoryAvailability.EXPERIMENTAL
    assert row.updated_by == "operator"
    assert row.rationale == "14-day metrics passed"


def test_other_category_cannot_be_exposed_to_users(db_session) -> None:
    with pytest.raises(ValueError, match="OTHER"):
        CategorySettingsService(db_session).set_status(
            Category.OTHER,
            CategoryAvailability.ENABLED,
            actor="operator",
            rationale="invalid",
            now=NOW,
        )
