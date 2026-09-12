from __future__ import annotations

import asyncio
import json
from pathlib import Path

from classmarker_crawler.pdf import PdfExporter, render_test_html, sanitize_filename
from classmarker_crawler.pdf_cli import load_and_filter_tests


def test_sanitize_filename():
    assert sanitize_filename("Test / Name : With * Special? Chars") == "Test _ Name _ With _ Special_ Chars"
    assert sanitize_filename("Test/Name") == "Test_Name"
    assert sanitize_filename("   A   B   ") == "A B"
    assert sanitize_filename("") == "untitled"


def test_render_test_html_detailed():
    test_data = {
        "test_name": "Math Practice 1",
        "student_name": "Alex",
        "points_scored": 1,
        "points_available": 2,
        "percentage": 50,
        "duration": "00:10:00",
        "date_finished": "2026-09-12",
        "questions": [
            {
                "number": 1,
                "html": "What is 2 + 2?",
                "points_scored": 1,
                "points_available": 1,
                "status": "correct",
                "answers": [
                    {"label": "A", "text": "4", "selected": True, "correct": True},
                    {"label": "B", "text": "5", "selected": False, "correct": False},
                ],
            },
            {
                "number": 2,
                "html": "Solve x = 10",
                "points_scored": 0,
                "points_available": 1,
                "status": "incorrect",
                "answer_given": {"text": "5", "correct": False},
                "accepted_answers": [{"text": "10"}],
            },
        ],
    }

    html = render_test_html(test_data, show_answers=True)
    assert "Math Practice 1" in html
    assert "Alex" in html
    assert "50%" in html
    assert "badge-correct" in html
    assert 'class="option opt-correct-selected"' in html
    assert "freetext-incorrect" in html
    assert "Accepted Answer(s):" in html


def test_render_test_html_exam_mode():
    test_data = {
        "test_name": "Math Practice 1",
        "student_name": "Alex",
        "points_scored": 1,
        "points_available": 2,
        "questions": [
            {
                "number": 1,
                "html": "What is 2 + 2?",
                "points_available": 1,
                "answers": [
                    {"label": "A", "text": "4", "selected": True, "correct": True},
                ],
            },
        ],
    }

    html = render_test_html(test_data, show_answers=False)
    assert "Math Practice 1" in html
    # In exam mode, options are neutral and no tags or answer badges in body
    assert 'class="option opt-exam"' in html
    assert 'class="badge badge-correct"' not in html
    assert '<span class="opt-tag' not in html


def test_load_and_filter_tests(tmp_path: Path):
    sample = [
        {"test_name": "Alpha Test", "student_name": "John Doe"},
        {"test_name": "Beta Test", "student_name": "Jane Smith"},
        {"test_name": "Gamma Test", "student_name": "John Wayne"},
    ]
    file_path = tmp_path / "tests.json"
    file_path.write_text(json.dumps(sample), encoding="utf-8")

    # Index filter
    res = load_and_filter_tests(file_path, test_filter="1")
    assert len(res) == 1
    assert res[0]["test_name"] == "Beta Test"

    # Substring filter
    res = load_and_filter_tests(file_path, test_filter="John")
    assert len(res) == 2

    # Limit
    res = load_and_filter_tests(file_path, limit=2)
    assert len(res) == 2


def test_pdf_export_execution(tmp_path: Path):
    sample_tests = [
        {
            "test_name": "Sample Test",
            "student_name": "Tester",
            "points_scored": 1,
            "points_available": 1,
            "questions": [
                {
                    "number": 1,
                    "html": "Question sample",
                    "points_scored": 1,
                    "points_available": 1,
                    "status": "correct",
                    "answers": [{"label": "A", "text": "Opt A", "selected": True, "correct": True}],
                }
            ],
        }
    ]

    out_dir = tmp_path / "pdfs"
    exporter = PdfExporter(base_dir=tmp_path, show_answers=True, workers=1)

    paths = asyncio.run(exporter.export_tests(sample_tests, out_dir))

    assert len(paths) == 1
    assert paths[0].exists()
    assert paths[0].stat().st_size > 0

