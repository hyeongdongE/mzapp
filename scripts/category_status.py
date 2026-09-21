from __future__ import annotations

import argparse

from app.db import session_scope
from app.models.enums import Category, CategoryAvailability
from app.product.categories import CategorySettingsService


def main() -> None:
    parser = argparse.ArgumentParser(description="View or change user category availability")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("list")
    setter = subparsers.add_parser("set")
    setter.add_argument(
        "category", choices=[item.value for item in Category if item is not Category.OTHER]
    )
    setter.add_argument("status", choices=[item.value for item in CategoryAvailability])
    setter.add_argument("--actor", required=True)
    setter.add_argument("--reason", required=True)
    args = parser.parse_args()

    with session_scope() as session:
        service = CategorySettingsService(session)
        if args.action == "set":
            service.set_status(
                Category(args.category),
                CategoryAvailability(args.status),
                actor=args.actor,
                rationale=args.reason,
            )
        for row in service.list():
            print(
                f"{row.category.value}\t{row.status.value}\t{row.updated_by}\t{row.rationale}"
            )


if __name__ == "__main__":
    main()
