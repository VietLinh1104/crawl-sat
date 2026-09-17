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


def test_retry_errors_filters_and_replaces(tmp_path):
    checkpoint_path = tmp_path / "questions.json"
    initial_records = [
        {"result_url": "https://example.test/success", "questions": [{"text": "Q1"}]},
        {"result_url": "https://example.test/failed", "error": "Timeout", "questions": []},
        {"result_url": "https://example.test/empty", "questions": []},
    ]
    ResultDetailsCrawler._write_checkpoint(checkpoint_path, initial_records)

    loaded = ResultDetailsCrawler._load_checkpoint(checkpoint_path)
    failed_urls = {
        item.get("result_url")
        for item in loaded
        if "error" in item or len(item.get("questions", [])) == 0
    }
    assert failed_urls == {
        "https://example.test/failed",
        "https://example.test/empty",
    }
