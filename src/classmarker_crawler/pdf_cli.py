from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from .pdf import PdfExporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export ClassMarker test questions & results to printable A4 PDF documents."
    )
    parser.add_argument(
        "--input",
        default="output/classmarker_questions.json",
        help="Path to questions JSON file (default: output/classmarker_questions.json)",
    )
    parser.add_argument(
        "--output-dir",
        default="output/pdfs",
        help="Directory where PDF files will be saved (default: output/pdfs)",
    )
    parser.add_argument(
        "--test",
        help="Filter by test index (0-based) or substring in test/student name",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of tests to export",
    )
    parser.add_argument(
        "--no-answers",
        action="store_true",
        help="Export blank exam paper (hides answers, scores, and correct indicators)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent browser pages (default: 4)",
    )
    return parser


def load_and_filter_tests(
    input_path: Path,
    test_filter: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError(f"Expected a JSON list of tests in {input_path}")

    filtered = data
    if test_filter is not None:
        # Check if filter is integer index
        if test_filter.isdigit():
            idx = int(test_filter)
            if 0 <= idx < len(data):
                filtered = [data[idx]]
            else:
                raise IndexError(f"Test index {idx} out of range (0 to {len(data)-1})")
        else:
            q = test_filter.lower()
            filtered = [
                t for t in data
                if q in (t.get("test_name") or "").lower() or q in (t.get("student_name") or "").lower()
            ]

    if limit is not None and limit > 0:
        filtered = filtered[:limit]

    return filtered


async def async_main(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    tests = load_and_filter_tests(input_path, args.test, args.limit)
    if not tests:
        print(f"No tests matched criteria from {input_path}")
        return

    mode_label = "Blank Exam" if args.no_answers else "Detailed Results"
    print(
        f"Exporting {len(tests)} test(s) to PDF [{mode_label}] using {max(1, args.workers)} worker(s)..."
    )

    base_dir = input_path.parent
    exporter = PdfExporter(
        base_dir=base_dir,
        show_answers=not args.no_answers,
        workers=args.workers,
    )

    completed_count = 0

    def progress(idx: int, total: int, dest: Path) -> None:
        nonlocal completed_count
        completed_count += 1
        print(f"[{completed_count}/{total}] Exported: {dest.name}", flush=True)

    results = await exporter.export_tests(tests, output_dir, progress_callback=progress)
    print(f"\nDone! Exported {len(results)} PDF file(s) to: {output_dir.resolve()}")


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
