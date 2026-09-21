import pytest
from sqlalchemy import func, select

from app.models.enums import DataMode
from app.models.tables import ProductTrendCard
from app.product.demo import DemoDataService


def test_demo_seed_refuses_when_explicit_mode_is_disabled(db_session) -> None:
    with pytest.raises(RuntimeError, match="DEMO_MODE_ENABLED"):
        DemoDataService(db_session, enabled=False).seed()


def test_demo_seed_is_idempotent_and_covers_four_interest_categories(db_session) -> None:
    service = DemoDataService(db_session, enabled=True)

    assert service.seed() == 4
    assert service.seed() == 0
    cards = list(
        db_session.scalars(
            select(ProductTrendCard).where(ProductTrendCard.data_mode == DataMode.DEMO)
        )
    )

    assert {card.category.value for card in cards} == {
        "ENTERTAINMENT",
        "AI_TECH",
        "FOOD",
        "GAME",
    }
    assert all(card.fixture_approved for card in cards)
    assert all("DEMO" in card.title for card in cards)


def test_demo_cleanup_preview_and_execute_never_delete_live_rows(db_session) -> None:
    service = DemoDataService(db_session, enabled=True)
    service.seed()

    assert service.cleanup(execute=False) == 4
    assert service.cleanup(execute=True) == 4
    assert db_session.scalar(
        select(func.count()).select_from(ProductTrendCard).where(
            ProductTrendCard.data_mode == DataMode.DEMO
        )
    ) == 0
