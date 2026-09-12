from __future__ import annotations

import asyncio
import html
import re
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, async_playwright


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """Sanitize string to be used safely as a filename."""
    cleaned = re.sub(r'[\\/*?:"<>|]+', "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_length].strip()


def _format_points(val: float | None) -> str:
    if val is None:
        return "0"
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return f"{val:.1f}"


def render_test_html(
    test: dict[str, Any],
    show_answers: bool = True,
    base_dir: Path | None = None,
) -> str:
    """Render a single test result into a clean, print-optimized HTML document."""
    test_name = html.escape(str(test.get("test_name") or "ClassMarker Test"))
    student_name = html.escape(str(test.get("student_name") or "Student"))
    duration = html.escape(str(test.get("duration") or "-"))
    date_finished = html.escape(str(test.get("date_finished") or test.get("date_started") or "-"))

    points_scored = test.get("points_scored")
    points_available = test.get("points_available")
    percentage = test.get("percentage")

    score_text = f"{_format_points(points_scored)} / {_format_points(points_available)}"
    pct_text = f"{percentage}%" if percentage is not None else "-"

    questions = test.get("questions", [])

    # Build Header HTML
    if show_answers:
        stats_html = f"""
        <div class="stats-grid">
            <div class="stat-card">
                <span class="stat-label">Score</span>
                <span class="stat-value">{score_text}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Percentage</span>
                <span class="stat-value highlight">{pct_text}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Duration</span>
                <span class="stat-value">{duration}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Finished Date</span>
                <span class="stat-value date">{date_finished}</span>
            </div>
        </div>
        """
    else:
        stats_html = f"""
        <div class="stats-grid">
            <div class="stat-card">
                <span class="stat-label">Total Questions</span>
                <span class="stat-value">{len(questions)}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Points Available</span>
                <span class="stat-value">{_format_points(points_available)}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Time Allowed</span>
                <span class="stat-value">{duration}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Date</span>
                <span class="stat-value date">________________</span>
            </div>
        </div>
        """

    # Build Questions HTML
    questions_html: list[str] = []
    for idx, q in enumerate(questions, start=1):
        q_num = q.get("number") or idx
        q_score = _format_points(q.get("points_scored"))
        q_avail = _format_points(q.get("points_available"))
        status = (q.get("status") or "unknown").lower()

        # Badge
        badge_html = ""
        if show_answers:
            if status == "correct":
                badge_html = f'<span class="badge badge-correct">✓ Correct ({q_score}/{q_avail} pt)</span>'
            elif status == "incorrect":
                badge_html = f'<span class="badge badge-incorrect">✗ Incorrect ({q_score}/{q_avail} pt)</span>'
            elif status == "unanswered":
                badge_html = f'<span class="badge badge-unanswered">- Unanswered (0/{q_avail} pt)</span>'
            else:
                badge_html = f'<span class="badge badge-neutral">{status.capitalize()} ({q_score}/{q_avail} pt)</span>'
        else:
            badge_html = f'<span class="badge badge-neutral">{q_avail} pt</span>'

        # Question Content
        q_content = q.get("html") or html.escape(q.get("text", "")).replace("\n", "<br>")

        # Handle answer choices
        answers = q.get("answers", [])
        answers_html: list[str] = []

        if answers:
            # Multiple choice question
            for opt in answers:
                label = html.escape(str(opt.get("label", "")))
                opt_content = opt.get("html") or html.escape(opt.get("text", "")).replace("\n", "<br>")
                selected = bool(opt.get("selected"))
                correct = bool(opt.get("correct"))

                if show_answers:
                    if selected and correct:
                        opt_class = "option opt-correct-selected"
                        indicator = '<span class="opt-tag tag-correct-selected">✓ Selected & Correct</span>'
                    elif selected and not correct:
                        opt_class = "option opt-incorrect-selected"
                        indicator = '<span class="opt-tag tag-incorrect-selected">✗ Your Selection</span>'
                    elif not selected and correct:
                        opt_class = "option opt-correct"
                        indicator = '<span class="opt-tag tag-correct">✓ Correct Answer</span>'
                    else:
                        opt_class = "option opt-neutral"
                        indicator = ""
                else:
                    opt_class = "option opt-exam"
                    indicator = ""

                answers_html.append(f"""
                <div class="{opt_class}">
                    <div class="opt-label">{label}</div>
                    <div class="opt-body">
                        <div class="opt-text">{opt_content}</div>
                        {indicator}
                    </div>
                </div>
                """)
        else:
            # Free-text / Grid-in question
            answer_given = q.get("answer_given")
            accepted_answers = q.get("accepted_answers", [])

            if show_answers:
                given_text = html.escape(answer_given.get("text", "-")) if answer_given else "-"
                is_correct = bool(answer_given and answer_given.get("correct"))
                given_class = "freetext-correct" if is_correct else "freetext-incorrect"

                accepted_list = []
                for acc in accepted_answers:
                    t = acc.get("text")
                    if t:
                        accepted_list.append(html.escape(t))
                accepted_text = ", ".join(accepted_list) if accepted_list else "Not specified"

                answers_html.append(f"""
                <div class="freetext-container">
                    <div class="freetext-row {given_class}">
                        <strong>Your Answer:</strong> <span class="freetext-val">{given_text}</span>
                    </div>
                    <div class="freetext-row freetext-accepted">
                        <strong>Accepted Answer(s):</strong> <span class="freetext-val">{accepted_text}</span>
                    </div>
                </div>
                """)
            else:
                answers_html.append("""
                <div class="freetext-exam-placeholder">
                    <strong>Your Answer:</strong> <span class="exam-line"></span>
                </div>
                """)

        options_block = "".join(answers_html)

        questions_html.append(f"""
        <div class="question-card">
            <div class="question-header">
                <div class="question-number">Question {q_num}</div>
                <div class="question-badge">{badge_html}</div>
            </div>
            <div class="question-body">
                {q_content}
            </div>
            <div class="question-answers">
                {options_block}
            </div>
        </div>
        """)

    all_questions_rendered = "\n".join(questions_html)
    base_tag = f'<base href="file://{base_dir.resolve()}/">' if base_dir else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
{base_tag}
<title>{test_name} - {student_name}</title>
<style>
@page {{
    size: A4;
    margin: 12mm 12mm 14mm 12mm;
    @bottom-right {{
        content: counter(page) " / " counter(pages);
        font-size: 8pt;
        color: #64748b;
    }}
}}

* {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.45;
    color: #1e293b;
    margin: 0;
    padding: 0;
    background: #ffffff;
}}

/* Header Banner */
.header-container {{
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    background: #f8fafc;
    padding: 14px 18px;
    margin-bottom: 20px;
    page-break-inside: avoid;
    break-inside: avoid;
}}

.test-title {{
    font-size: 16pt;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 6px 0;
}}

.student-meta {{
    font-size: 10.5pt;
    font-weight: 600;
    color: #475569;
    margin-bottom: 14px;
}}

.stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
}}

.stat-card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
}}

.stat-label {{
    font-size: 7.5pt;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
    font-weight: 600;
    margin-bottom: 2px;
}}

.stat-value {{
    font-size: 12pt;
    font-weight: 700;
    color: #0f172a;
}}

.stat-value.highlight {{
    color: #2563eb;
}}

.stat-value.date {{
    font-size: 9.5pt;
    font-weight: 600;
}}

/* Question Cards */
.question-card {{
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background: #ffffff;
    margin-bottom: 16px;
    padding: 12px 16px 14px 16px;
    page-break-inside: avoid;
    break-inside: avoid;
}}

.question-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 8px;
    margin-bottom: 10px;
}}

.question-number {{
    font-size: 10.5pt;
    font-weight: 700;
    color: #0f172a;
}}

.badge {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 8pt;
    font-weight: 600;
}}

.badge-correct {{
    background: #dcfce7;
    color: #15803d;
    border: 1px solid #bbf7d0;
}}

.badge-incorrect {{
    background: #fee2e2;
    color: #b91c1c;
    border: 1px solid #fecaca;
}}

.badge-unanswered {{
    background: #f1f5f9;
    color: #64748b;
    border: 1px solid #e2e8f0;
}}

.badge-neutral {{
    background: #f8fafc;
    color: #475569;
    border: 1px solid #e2e8f0;
}}

.question-body {{
    font-size: 9.5pt;
    color: #1e293b;
    margin-bottom: 12px;
}}

.question-body img,
.opt-text img {{
    max-width: 100%;
    max-height: 280px;
    display: block;
    margin: 8px auto;
    object-fit: contain;
    border-radius: 4px;
}}

/* Answer Options */
.question-answers {{
    display: flex;
    flex-direction: column;
    gap: 7px;
}}

.option {{
    display: flex;
    align-items: flex-start;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 9pt;
    transition: none;
}}

.opt-label {{
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #f1f5f9;
    color: #334155;
    font-weight: 700;
    font-size: 8.5pt;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-right: 10px;
    margin-top: 1px;
}}

.opt-body {{
    flex: 1;
}}

.opt-text {{
    color: #1e293b;
}}

.opt-tag {{
    display: inline-block;
    font-size: 7.5pt;
    font-weight: 600;
    margin-top: 3px;
    padding: 1px 6px;
    border-radius: 4px;
}}

/* Option Styles for Detailed Mode */
.opt-correct-selected {{
    background: #f0fdf4;
    border: 1.5px solid #22c55e;
}}
.opt-correct-selected .opt-label {{
    background: #22c55e;
    color: #ffffff;
}}
.tag-correct-selected {{
    background: #dcfce7;
    color: #15803d;
}}

.opt-incorrect-selected {{
    background: #fef2f2;
    border: 1.5px solid #ef4444;
}}
.opt-incorrect-selected .opt-label {{
    background: #ef4444;
    color: #ffffff;
}}
.tag-incorrect-selected {{
    background: #fee2e2;
    color: #b91c1c;
}}

.opt-correct {{
    background: #f8fafc;
    border: 1.5px dashed #22c55e;
}}
.opt-correct .opt-label {{
    background: #dcfce7;
    color: #15803d;
}}
.tag-correct {{
    background: #dcfce7;
    color: #15803d;
}}

.opt-neutral {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
}}

.opt-exam {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
}}

/* Free text / Grid-in */
.freetext-container {{
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 9pt;
}}

.freetext-row.freetext-correct {{
    color: #15803d;
}}

.freetext-row.freetext-incorrect {{
    color: #b91c1c;
}}

.freetext-row.freetext-accepted {{
    color: #334155;
    border-top: 1px dashed #e2e8f0;
    padding-top: 4px;
}}

.freetext-exam-placeholder {{
    padding: 10px 0;
    font-size: 9.5pt;
}}

.exam-line {{
    display: inline-block;
    width: 200px;
    border-bottom: 1.5px solid #475569;
    margin-left: 8px;
}}
</style>
</head>
<body>

<div class="header-container">
    <h1 class="test-title">{test_name}</h1>
    <div class="student-meta">Student: {student_name}</div>
    {stats_html}
</div>

{all_questions_rendered}

</body>
</html>
"""


class PdfExporter:
    """Exports test data to PDF documents using Playwright headless Chromium."""

    def __init__(self, base_dir: Path, show_answers: bool = True, workers: int = 4):
        self.base_dir = base_dir
        self.show_answers = show_answers
        self.workers = max(1, workers)

    async def _export_one(
        self,
        browser: Browser,
        semaphore: asyncio.Semaphore,
        test: dict[str, Any],
        output_path: Path,
    ) -> None:
        async with semaphore:
            context = await browser.new_context()
            page = await context.new_page()
            try:
                html_content = render_test_html(
                    test,
                    show_answers=self.show_answers,
                    base_dir=self.base_dir,
                )
                await page.set_content(html_content, wait_until="load")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                await page.pdf(
                    path=str(output_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "12mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
                )
            finally:
                await page.close()
                await context.close()

    async def export_tests(
        self,
        tests: list[dict[str, Any]],
        output_dir: Path,
        progress_callback: Any = None,
    ) -> list[Path]:
        """Export multiple tests into individual PDF files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        semaphore = asyncio.Semaphore(self.workers)

        exported_paths: list[Path] = []
        name_counts: dict[str, int] = {}

        tasks = []
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                for idx, test in enumerate(tests):
                    t_name = sanitize_filename(test.get("test_name") or f"Test_{idx+1}")
                    s_name = sanitize_filename(test.get("student_name") or "Student")
                    base_name = f"{t_name} - {s_name}"

                    # Handle duplicate filenames
                    count = name_counts.get(base_name, 0)
                    name_counts[base_name] = count + 1
                    if count > 0:
                        file_name = f"{base_name} ({count+1}).pdf"
                    else:
                        file_name = f"{base_name}.pdf"

                    dest_path = output_dir / file_name
                    exported_paths.append(dest_path)

                    async def run_task(t: dict[str, Any], pth: Path, i: int) -> None:
                        await self._export_one(browser, semaphore, t, pth)
                        if progress_callback:
                            progress_callback(i + 1, len(tests), pth)

                    tasks.append(run_task(test, dest_path, idx))

                await asyncio.gather(*tasks)
            finally:
                await browser.close()

        return exported_paths
