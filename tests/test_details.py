import json

from classmarker_crawler.details import ResultDetailsCrawler, load_result_rows


def test_load_result_rows_filters_rows_without_links(tmp_path):
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps([{"Name": "A", "result_link": "https://example.test/1"}, {"Name": "B"}]),
        encoding="utf-8",
    )
    assert load_result_rows(path) == [
        {"Name": "A", "result_link": "https://example.test/1"}
    ]


def test_checkpoint_round_trip(tmp_path):
    path = tmp_path / "questions.json"
    records = [{"result_url": "https://example.test/1", "questions": []}]
    ResultDetailsCrawler._write_checkpoint(path, records)
    assert ResultDetailsCrawler._load_checkpoint(path) == records
