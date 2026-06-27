from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .config import Settings
from .crawler import ClassMarkerCrawler
from .exporters import export_csv, export_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl authorized ClassMarker table data")
    parser.add_argument("--url", help="ClassMarker target URL; overrides .env")
    parser.add_argument("--output", default="output/classmarker_data", help="Output path without extension")
    parser.add_argument("--format", choices=("json", "csv", "both"), default="both")
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between pages in seconds")
    parser.add_argument("--headed", action="store_true", help="Show Chromium window")
    parser.add_argument("--manual-login", action="store_true", help="Log in manually (requires --headed)")
    return parser


async def async_main(args: argparse.Namespace) -> None:
    settings = Settings.from_env(args.url)
    crawler = ClassMarkerCrawler(
        settings,
        headed=args.headed,
        manual_login=args.manual_login,
        delay=args.delay,
        max_pages=args.max_pages,
    )
    result = await crawler.run()
    base = Path(args.output)
    if args.format in ("json", "both"):
        export_json(result, base.with_suffix(".json"))
    if args.format in ("csv", "both"):
        export_csv(result, base.with_suffix(".csv"))

    row_count = sum(len(table["rows"]) for page in result.pages for table in page["tables"])
    print(f"Done: {len(result.pages)} page(s), {row_count} row(s), output={base.parent}")


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()

