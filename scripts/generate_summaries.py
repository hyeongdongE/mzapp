from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from sqlalchemy import func, select

from app.ai.summary import SummaryService
from app.db import session_scope
from app.models.tables import TrendSnapshot
from app.product.cards import ProductCardService
from app.services.pipeline import PipelineVersions
from scripts.collect import parse_as_of


async def generate(as_of_text: str | None, top_n: int) -> None:
    versions = PipelineVersions()
    with session_scope() as session:
        as_of: datetime | None
        if as_of_text is None:
            as_of = session.scalar(
                select(func.max(TrendSnapshot.as_of)).where(
                    TrendSnapshot.score_version == versions.score
                )
            )
        else:
            as_of = parse_as_of(as_of_text)
        if as_of is None:
            print("snapshots=0 claims=0 provider=evidence-only")
            return
        claims = await SummaryService(session).generate_top(
            as_of=as_of,
            top_n=top_n,
            prompt_version=versions.prompt,
            score_version=versions.score,
        )
        product_cards = ProductCardService(session).sync_live(as_of)
        publishable = sum(claim.publishable for claim in claims)
        print(
            f"as_of={as_of.isoformat()} claims={len(claims)} "
            f"publishable={publishable} product_cards={product_cards} provider=evidence-only"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate evidence-only trend summaries")
    parser.add_argument("--as-of")
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()
    if args.top_n <= 0:
        parser.error("--top-n must be positive")
    asyncio.run(generate(args.as_of, args.top_n))


if __name__ == "__main__":
    main()
