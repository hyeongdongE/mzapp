from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.brief_quality_database import load_brief_quality_facts
from app.evaluation.brief_quality_metrics import aggregate_brief_quality
from app.evaluation.brief_quality_models import BriefQualityReport


def report_to_dict(report: BriefQualityReport) -> dict[str, Any]:
    return _primitive(asdict(report))


def render_brief_quality_json(report: BriefQualityReport) -> str:
    return json.dumps(report_to_dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_brief_quality_markdown(report: BriefQualityReport) -> str:
    data = report_to_dict(report)
    metrics = data["metrics"]
    useful = metrics["usefulBriefRate"]
    rate = "N/A" if useful["rate"] is None else f"{useful['rate'] * 100:.2f}%"
    lines = [
        "# SoloPilot Daily Brief Quality Validation",
        "",
        f"Sample status: `{data['sampleStatus']}`",
        "",
        "> This status describes the minimum evaluation sample only; "
        "it makes no product-quality conclusion.",
        "",
        f"Reviewer: `{data['reviewer']}`",
        f"Period: `{data['startDate']}` through `{data['endDate']}` (Asia/Seoul Brief dates)",
        f"Generated: `{data['generatedAt']}`",
        "",
        "## Version provenance",
        "",
        f"- Report schema: `{data['reportSchemaVersion']}`",
        f"- Pipeline: {_joined(data['pipelineVersions'])}",
        f"- Generation: {_joined(data['generationVersions'])}",
        f"- Clustering: {_joined(data['clusteringVersions'])}",
        f"- Assessment: {_joined(data['assessmentVersions'])}",
        "",
        "## Useful Brief Rate",
        "",
        f"{useful['numerator']} / {useful['denominator']} = **{rate}**",
        "",
        "## Active review effort (`active_review_seconds`)",
        "",
        "This is internal review effort, not actual `/today` reading time.",
        f"P50: {_display(metrics['activeReviewSecondsP50'])} seconds",
        f"P95: {_display(metrics['activeReviewSecondsP95'])} seconds",
        "Active review seconds by day: "
        f"`{json.dumps(metrics['activeReviewSecondsByDay'], sort_keys=True)}`",
        "",
        "## Review counts",
        "",
        f"- Reviewed Briefs: {metrics['reviewedBriefCount']}",
        f"- Reviewed dates: {metrics['reviewedDateCount']}",
        f"- Reviewed items: {metrics['reviewedItemCount']}",
        f"- Missing events per day: `{json.dumps(metrics['missingEventsPerDay'], sort_keys=True)}`",
        "",
        "## Categorical distributions",
        "",
    ]
    for key in (
        "eventSelection",
        "factCorrectness",
        "interpretationQuality",
        "watchUsefulness",
        "verbosity",
        "evidenceSetUsefulness",
        "missingEventDiscoverySources",
    ):
        lines.append(f"- {key}: `{json.dumps(metrics[key], sort_keys=True)}`")
    lines.extend(
        [
            "",
            "## Structured defects",
            "",
            f"- Incorrect merge: {_rate_line(metrics['incorrectMerge'])}",
            f"- Duplicate escape: {_rate_line(metrics['duplicateEscape'])}",
            "- Incorrect-merge links: "
            f"`{json.dumps(metrics['incorrectMergeLinks'], sort_keys=True)}`",
            "- Duplicate-escape links: "
            f"`{json.dumps(metrics['duplicateEscapeLinks'], sort_keys=True)}`",
            "",
            "## Included Brief dates",
            "",
        ]
    )
    lines.extend(
        f"- {row['briefDate']} · Brief #{row['briefId']} v{row['briefVersion']}"
        for row in data["includedDates"]
    )
    if not data["includedDates"]:
        lines.append("- None")
    lines.extend(["", "## Operational and excluded dates", ""])
    lines.extend(
        f"- Operational: {row['briefDate']} · Brief #{row['briefId']} · {row['status']}"
        for row in data["operationalDates"]
    )
    lines.extend(
        f"- Excluded: {row['briefDate']} · Brief #{row['briefId']} · {row['reason']}"
        for row in data["excludedDates"]
    )
    if not data["operationalDates"] and not data["excludedDates"]:
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def write_report_pair_atomic(
    json_path: Path, markdown_path: Path, json_content: str, markdown_content: str
) -> None:
    stages: list[Path] = []
    backups: dict[Path, Path] = {}
    installed: set[Path] = set()
    try:
        stages.append(_stage_text(json_path, json_content))
        stages.append(_stage_text(markdown_path, markdown_content))
        for target in (json_path, markdown_path):
            if target.exists():
                backup = _reserve_temp(target, ".backup")
                shutil.copy2(target, backup)
                backups[target] = backup
        for stage, target in zip(stages, (json_path, markdown_path), strict=True):
            os.replace(stage, target)
            installed.add(target)
    except BaseException:
        for target in installed:
            if target in backups:
                os.replace(backups[target], target)
            else:
                target.unlink(missing_ok=True)
        raise
    finally:
        for path in [*stages, *backups.values()]:
            path.unlink(missing_ok=True)


def _stage_text(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    path = _reserve_temp(target, ".tmp")
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _reserve_temp(target: Path, suffix: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=suffix)
    os.close(descriptor)
    return Path(name)


def build_brief_quality_report(
    session: Session, *, reviewer: str, start_date: date, end_date: date
) -> dict[str, Any]:
    facts = load_brief_quality_facts(
        session, reviewer=reviewer, start_date=start_date, end_date=end_date
    )
    return report_to_dict(aggregate_brief_quality(facts, generated_at=datetime.now(UTC)))


def _primitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {_camel(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


def _display(value: Any) -> str:
    return "N/A" if value is None else str(value)


def _joined(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "N/A"


def _rate_line(value: dict[str, Any]) -> str:
    rate = "N/A" if value["rate"] is None else f"{value['rate'] * 100:.2f}%"
    return f"{value['numerator']} / {value['denominator']} = {rate}"
