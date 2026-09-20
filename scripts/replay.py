from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, time

from app.db import session_scope
from app.services.replay import ReplayService


def parse_boundary(value: str, *, end: bool) -> datetime:
    try:
        if "T" not in value and " " not in value:
            parsed_date = date.fromisoformat(value)
            return datetime.combine(parsed_date, time.max if end else time.min, tzinfo=UTC)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("range values must be ISO dates or datetimes") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("datetime range values must include a timezone")
    return parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay stored official trend observations")
    parser.add_argument("--from", dest="from_text", required=True)
    parser.add_argument("--to", dest="to_text", required=True)
    parser.add_argument("--score-version", required=True)
    parser.add_argument("--normalizer-version", default="normalizer-v1")
    parser.add_argument("--entity-version", default="entity-v1")
    parser.add_argument("--classifier-version", default="classifier-v1")
    parser.add_argument("--prompt-version", default="prompt-v1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    from_ = parse_boundary(args.from_text, end=False)
    to = parse_boundary(args.to_text, end=True)
    with session_scope() as session:
        result = ReplayService(session).run(
            from_,
            to,
            score_version=args.score_version,
            normalizer_version=args.normalizer_version,
            entity_version=args.entity_version,
            classifier_version=args.classifier_version,
            prompt_version=args.prompt_version,
            dry_run=args.dry_run,
        )
    print(
        f"run_id={result.run_id or 'DRY_RUN'} snapshots={result.snapshot_count} "
        f"digest={result.snapshot_digest}"
    )


if __name__ == "__main__":
    main()
