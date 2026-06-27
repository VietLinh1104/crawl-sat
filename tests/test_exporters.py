import csv
import json

from classmarker_crawler.crawler import CrawlResult
from classmarker_crawler.exporters import export_csv, export_json


def sample_result() -> CrawlResult:
    return CrawlResult(
        source_url="https://www.classmarker.com/a/tests/results/",
        pages=[
            {
                "page": 1,
                "url": "https://www.classmarker.com/a/tests/results/",
                "tables": [
                    {
                        "index": 0,
                        "headers": ["Name", "Score"],
                        "rows": [
                            {"Name": "Not finished", "column_5": "Start"},
                            {
                                "Name": "An",
                                "Score": "9",
                                "column_5": "Results",
                                "result_link": "https://www.classmarker.com/test/results/?test_id=1",
                            },
                        ],
                    }
                ],
            }
        ],
    )


def test_export_json(tmp_path):
    path = tmp_path / "result.json"
    export_json(sample_result(), path)
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["Name"] == "An"
    assert rows[0]["result_link"].endswith("test_id=1")


def test_export_csv(tmp_path):
    path = tmp_path / "result.csv"
    export_csv(sample_result(), path)
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert rows[0]["Name"] == "An"
    assert rows[0]["Score"] == "9"
