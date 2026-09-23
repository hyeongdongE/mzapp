from __future__ import annotations

from app.models.tables import Base


def test_schema_contains_it_intelligence_tables() -> None:
    assert {
        "source_health",
        "raw_items",
        "event_clusters",
        "event_cluster_items",
        "intelligence_entities",
        "event_entity_links",
        "event_evidence",
        "event_facts",
        "event_fact_evidence",
        "event_assessments",
        "daily_briefs",
        "brief_items",
        "brief_item_facts",
    } <= set(Base.metadata.tables)


def test_raw_items_reference_fetch_provenance_without_embedding_payload() -> None:
    table = Base.metadata.tables["raw_items"]

    assert "raw_fetch_id" in table.columns
    assert "raw_payload" not in table.columns
    assert {fk.target_fullname for fk in table.foreign_keys} == {"raw_fetches.id"}
    assert any(
        constraint.name == "uq_raw_item_source_external_version"
        for constraint in table.constraints
    )


def test_fact_level_provenance_foreign_keys_are_present() -> None:
    fact_evidence = Base.metadata.tables["event_fact_evidence"]
    brief_fact = Base.metadata.tables["brief_item_facts"]

    assert {fk.target_fullname for fk in fact_evidence.foreign_keys} == {
        "event_facts.id",
        "event_evidence.id",
    }
    assert {fk.target_fullname for fk in brief_fact.foreign_keys} == {
        "brief_items.id",
        "event_facts.id",
        "event_evidence.id",
    }


def test_brief_and_cluster_membership_have_idempotency_constraints() -> None:
    brief_constraints = Base.metadata.tables["daily_briefs"].constraints
    item_constraints = Base.metadata.tables["brief_items"].constraints
    membership_constraints = Base.metadata.tables["event_cluster_items"].constraints

    assert any(item.name == "uq_daily_brief_date_version" for item in brief_constraints)
    assert any(item.name == "uq_brief_item_position" for item in item_constraints)
    assert any(item.name == "uq_event_cluster_raw_item" for item in membership_constraints)


def test_source_health_has_runtime_state_but_no_policy_fields() -> None:
    columns = set(Base.metadata.tables["source_health"].columns.keys())

    assert {
        "source",
        "last_attempt_at",
        "last_success_at",
        "last_failure_at",
        "consecutive_failures",
        "last_error_code",
        "freshness_state",
        "covered_through",
    } <= columns
    assert "store_full_content" not in columns
    assert "public_summary" not in columns
