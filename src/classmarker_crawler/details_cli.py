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
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Chạy lại các đề thi bị lỗi hoặc chưa thu thập được câu hỏi nào",
    )
    return parser


async def async_main(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(
            f"Lỗi: Không tìm thấy '{input_path}'.\n"
            f"Vui lòng chạy lệnh 'classmarker-crawl' trước để tạo danh sách bài thi!"
        )
    rows = load_result_rows(input_path)
    crawler = ResultDetailsCrawler(
        Settings.from_env(),
        headed=args.headed,
        manual_login=args.manual_login,
        delay=args.delay,
    )
    details = await crawler.run(rows, Path(args.output), retry_errors=args.retry_errors)
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
