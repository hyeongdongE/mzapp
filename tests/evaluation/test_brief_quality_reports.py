from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from app.evaluation.brief_quality_metrics import aggregate_brief_quality
from app.evaluation.brief_quality_models import (
    BriefQualityFacts,
    ExcludedDateFact,
    OperationalDateFact,
)
from app.evaluation.brief_quality_reports import (
    render_brief_quality_json,
    render_brief_quality_markdown,
    write_report_pair_atomic,
)


def sample_report():
    facts = BriefQualityFacts(
        reviewer="owner",
        start_date=date(2026, 9, 20),
        end_date=date(2026, 9, 24),
        operational_dates=(OperationalDateFact(1, date(2026, 9, 20), 1, "LOW_SIGNAL_DAY"),),
        included_dates=(),
        excluded_dates=(
            ExcludedDateFact(1, date(2026, 9, 20), 1, "LOW_SIGNAL_DAY", "LOW_SIGNAL_DAY"),
        ),
    )
    return aggregate_brief_quality(facts, generated_at=datetime(2026, 9, 24, 10, tzinfo=UTC))


def test_json_is_canonical_and_contains_provenance_dates_and_metrics() -> None:
    payload = json.loads(render_brief_quality_json(sample_report()))

    assert payload["reportSchemaVersion"] == "brief-quality-report-v1"
    assert payload["sampleStatus"] == "INSUFFICIENT_VALIDATION_DAYS"
    assert payload["reviewer"] == "owner"
    assert payload["generatedAt"] == "2026-09-24T10:00:00+00:00"
    assert payload["pipelineVersions"] == []
    assert payload["generationVersions"] == []
    assert payload["clusteringVersions"] == []
    assert payload["assessmentVersions"] == []
    assert payload["operationalDates"][0]["status"] == "LOW_SIGNAL_DAY"
    assert payload["excludedDates"][0]["briefId"] == 1
    assert payload["metrics"]["usefulBriefRate"]["rate"] is None


def test_markdown_renders_model_and_labels_review_effort_without_success_claim() -> None:
    markdown = render_brief_quality_markdown(sample_report())

    assert "Active review effort (`active_review_seconds`)" in markdown
    assert "N/A" in markdown
    assert "LOW_SIGNAL_DAY" in markdown
    assert "minimum evaluation sample" in markdown
    assert "quality pass" not in markdown.casefold()
    assert "Reviewed dates: 0" in markdown
    assert "Missing events per day" in markdown
    assert "Active review seconds by day" in markdown


def test_pair_writer_preserves_existing_targets_when_staging_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    json_path.write_text("old-json", encoding="utf-8")
    markdown_path.write_text("old-markdown", encoding="utf-8")
    calls = 0

    from app.evaluation import brief_quality_reports

    original = brief_quality_reports._stage_text

    def fail_second(path, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return original(path, content)

    monkeypatch.setattr(brief_quality_reports, "_stage_text", fail_second)
    with pytest.raises(OSError, match="disk full"):
        write_report_pair_atomic(json_path, markdown_path, "new-json", "new-markdown")

    assert json_path.read_text(encoding="utf-8") == "old-json"
    assert markdown_path.read_text(encoding="utf-8") == "old-markdown"
    assert not list(tmp_path.glob("*.tmp"))
