from __future__ import annotations

import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, date, datetime

import pytest

import scripts.collect as collect_script
from app.collectors.base import CollectionBatch, MalformedPayload, SourceItem
from app.config.settings import get_settings
from app.models.enums import Source
from app.models.tables import SourceHealth
from scripts.collect import build_collectors, parse_date


def test_collect_script_can_be_executed_directly() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/collect.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Collect official trend signals" in result.stdout
    assert "geeknews" in result.stdout
    assert "hacker-news" in result.stdout
    assert "github" in result.stdout


def test_parse_date_accepts_wikimedia_backfill_date() -> None:
    assert parse_date("2026-09-18") == date(2026, 9, 18)


def test_all_collects_only_enabled_intelligence_sources() -> None:
    collectors = build_collectors("all", object(), get_settings(), target_date=None)

    assert {collector.source for collector in collectors} == {
        Source.GEEKNEWS,
        Source.HACKER_NEWS,
        Source.GITHUB_RELEASES,
        Source.OFFICIAL_CLOUDFLARE,
        Source.OFFICIAL_AWS,
    }


def test_collect_cli_exits_nonzero_after_isolated_failure(monkeypatch) -> None:
    async def failed_collect(*_args, **_kwargs):
        return [
            {
                "source": Source.HACKER_NEWS.value,
                "run_id": 0,
                "items": 0,
                "error": "MALFORMED_PAYLOAD",
            }
        ]

    monkeypatch.setattr(collect_script, "collect", failed_collect)
    monkeypatch.setattr(sys, "argv", ["collect.py", "--source", "hacker-news"])

    with pytest.raises(SystemExit) as exc_info:
        collect_script.main()

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_direct_collection_commits_failure_and_continues(
    monkeypatch, db_session
) -> None:
    as_of = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)

    class BadCollector:
        source = Source.HACKER_NEWS

        async def collect(self, _as_of: datetime) -> CollectionBatch:
            raise MalformedPayload("bad response")

    class GoodCollector:
        source = Source.GEEKNEWS

        async def collect(self, _as_of: datetime) -> CollectionBatch:
            return CollectionBatch(
                source=self.source,
                collected_at=as_of,
                request_url="https://news.hada.io/rss/news",
                raw_bytes=b"<feed />",
                items=[
                    SourceItem(
                        source_item_id="geeknews:direct",
                        source_timestamp=as_of,
                        observed_at=as_of,
                        canonical_text="Direct collection",
                        source_url="https://news.hada.io/topic?id=direct",
                        metrics={},
                        title="Direct collection",
                    )
                ],
                collector_version="fixture-v1",
                parser_version="fixture-v1",
                coverage_complete=True,
            )

    @contextmanager
    def fake_session_scope():
        yield db_session

    monkeypatch.setattr(
        collect_script,
        "build_collectors",
        lambda *_args, **_kwargs: [BadCollector(), GoodCollector()],
    )
    monkeypatch.setattr(collect_script, "session_scope", fake_session_scope)

    outputs = await collect_script.collect("all", as_of)

    assert [output.get("error") for output in outputs] == ["MALFORMED_PAYLOAD", None]
    failed = db_session.get(SourceHealth, (Source.HACKER_NEWS, "default"))
    healthy = db_session.get(SourceHealth, (Source.GEEKNEWS, "default"))
    assert failed is not None and failed.freshness_state == "FAILED"
    assert healthy is not None and healthy.freshness_state == "FRESH"
