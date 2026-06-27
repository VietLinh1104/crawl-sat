from __future__ import annotations

import csv
import json
from pathlib import Path

from .crawler import CrawlResult


def result_records(result: CrawlResult) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    for page_data in result.pages:
        for table in page_data["tables"]:
            for row in table["rows"]:
                if row.get("column_5") == "Results":
                    records.append(row)
    return records


def export_json(result: CrawlResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result_records(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_csv(result: CrawlResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = result_records(result)

    fieldnames: list[str] = []
    for record in records:
        for field in record:
            if field not in fieldnames:
                fieldnames.append(field)

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
