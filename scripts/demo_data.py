from __future__ import annotations

import argparse

from app.config.settings import get_settings
from app.db import session_scope
from app.product.demo import DemoDataService


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage isolated Trend Radar DEMO fixtures")
    parser.add_argument("action", choices=("seed", "clean"))
    parser.add_argument(
        "--execute", action="store_true", help="Required to execute cleanup; otherwise preview"
    )
    args = parser.parse_args()
    settings = get_settings()
    with session_scope() as session:
        service = DemoDataService(session, enabled=settings.demo_mode_enabled)
        if args.action == "seed":
            print(f"demo_created={service.seed()}")
        else:
            count = service.cleanup(execute=args.execute)
            print(f"demo_cards={count} executed={str(args.execute).lower()}")


if __name__ == "__main__":
    main()
