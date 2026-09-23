from __future__ import annotations

import argparse
from datetime import date

import pytest

from scripts.evaluate_brief_quality import parse_args, report_paths


def test_cli_requires_reviewer_and_date_range() -> None:
    with pytest.raises(SystemExit):
        parse_args([])


def test_cli_rejects_reversed_date_range() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="start date"):
        parse_args(
            [
                "--reviewer",
                "owner",
                "--start-date",
                "2026-09-24",
                "--end-date",
                "2026-09-20",
            ]
        )


def test_report_paths_are_deterministic(tmp_path) -> None:
    json_path, markdown_path = report_paths(tmp_path, date(2026, 9, 20), date(2026, 9, 24))
    assert json_path.name == "brief-quality-2026-09-20-2026-09-24.json"
    assert markdown_path.name == "brief-quality-2026-09-20-2026-09-24.md"
