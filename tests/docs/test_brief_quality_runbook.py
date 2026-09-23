from pathlib import Path


def test_runbook_preserves_real_dogfood_and_frozen_pipeline_contract() -> None:
    text = Path("docs/it-intelligence/daily-brief-quality-validation.md").read_text(
        encoding="utf-8"
    )

    required = (
        "1. Use `/today`",
        "2. Open `/internal/brief-quality`",
        "active_review_seconds",
        "review effort",
        "latest `PUBLISHED`",
        "LATEST_PUBLISHED_VERSION_UNREVIEWED",
        "LOW_SIGNAL_DAY",
        "operational record",
        "PostgreSQL is the source of truth",
        "uv run python scripts/evaluate_brief_quality.py",
        "five distinct real Brief dates",
        "VALIDATION_SAMPLE_COMPLETE",
        "Tooling Ready for Field Use",
        "5-day Quality Validation Complete",
        "IN_PROGRESS",
        "does not modify ranking, clustering, prompts, or source policy",
    )
    for phrase in required:
        assert phrase in text
