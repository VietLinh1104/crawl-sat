from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .config import Settings
from .details import ResultDetailsCrawler, load_result_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl questions and answers from result links")
    parser.add_argument("--input", default="output/classmarker_data.json")
    parser.add_argument("--output", default="output/classmarker_questions.json")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--manual-login", action="store_true")
    return parser


async def async_main(args: argparse.Namespace) -> None:
    rows = load_result_rows(Path(args.input))
    crawler = ResultDetailsCrawler(
        Settings.from_env(),
        headed=args.headed,
        manual_login=args.manual_login,
        delay=args.delay,
    )
    details = await crawler.run(rows, Path(args.output))
    question_count = sum(len(item["questions"]) for item in details)
    error_count = sum("error" in item for item in details)
    print(
        f"Done: {len(details)} result(s), {question_count} question(s), "
        f"{error_count} error(s), output={args.output}"
    )


def main() -> None:
    asyncio.run(async_main(build_parser().parse_args()))


if __name__ == "__main__":
    main()
