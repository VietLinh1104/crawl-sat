from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

from .crawler import ClassMarkerCrawler
from .config import Settings


class ResultDetailsCrawler:
    def __init__(
        self,
        settings: Settings,
        *,
        headed: bool = False,
        manual_login: bool = False,
        delay: float = 0.5,
    ) -> None:
        self.settings = settings
        self.delay = max(delay, 0.25)
        self.login = ClassMarkerCrawler(
            settings,
            headed=headed,
            manual_login=manual_login,
            delay=delay,
        )

    async def run(
        self,
        result_rows: list[dict[str, Any]],
        output_path: Path,
    ) -> list[dict[str, Any]]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        completed = self._load_checkpoint(output_path)
        completed_urls = {item.get("result_url") for item in completed}
        pending = [row for row in result_rows if row.get("result_link") not in completed_urls]

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=not self.login.headed)
            context_args: dict[str, Any] = {}
            if self.settings.auth_state.exists():
                context_args["storage_state"] = str(self.settings.auth_state)
            context = await browser.new_context(**context_args)
            try:
                page = await context.new_page()
                await self.login._open_target(page, context)
                total = len(result_rows)
                for index, row in enumerate(pending, start=len(completed) + 1):
                    url = row.get("result_link")
                    if not isinstance(url, str) or not url:
                        continue
                    try:
                        detail = await self._crawl_one(page, url, row)
                    except Exception as exc:  # Keep the checkpoint usable if one page fails.
                        detail = {
                            "result_url": url,
                            "source_row": row,
                            "error": f"{type(exc).__name__}: {exc}",
                            "questions": [],
                        }
                    completed.append(detail)
                    self._write_checkpoint(output_path, completed)
                    print(
                        f"[{index}/{total}] {detail.get('test_name') or row.get('Name')}: "
                        f"{len(detail['questions'])} question(s)",
                        flush=True,
                    )
                    await page.wait_for_timeout(int(self.delay * 1000))
            finally:
                await context.close()
                await browser.close()

        return completed

    async def _crawl_one(
        self,
        page: Page,
        url: str,
        source_row: dict[str, Any],
    ) -> dict[str, Any]:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        if not page.url.startswith(url.split("?", 1)[0]):
            raise RuntimeError(f"Unexpected redirect to {page.url}")
        await page.locator("#result-wrapper").wait_for(state="attached", timeout=30_000)

        detail = await page.evaluate(
            r"""
            () => {
              const clean = (value) => (value || "")
                .replace(/\u00a0/g, " ")
                .replace(/[ \t]+\n/g, "\n")
                .replace(/\n{3,}/g, "\n\n")
                .trim();
              const text = (selector, root = document) => {
                const element = root.querySelector(selector);
                return clean(element ? element.innerText : "");
              };
              const absoluteUrls = (selector, attribute, root) =>
                [...root.querySelectorAll(selector)]
                  .map((element) => element[attribute] || element.getAttribute(attribute))
                  .filter(Boolean);
              const numberValue = (selector) => {
                const value = text(selector);
                return value !== "" && !Number.isNaN(Number(value)) ? Number(value) : null;
              };

              const questions = [...document.querySelectorAll(".qd.card")].map((card, index) => {
                const qbox = card.querySelector(".qbox");
                const holder = card.querySelector(".qsholder");
                const pointsText = text(".headlinetoppoints", card);
                const points = pointsText.match(/([\d.]+)\s*\/\s*([\d.]+)/);
                const answers = [...card.querySelectorAll(".answholder tr")].map((row) => {
                  const rowClasses = row.classList;
                  const feedbackClasses = [...row.querySelectorAll(".feedback-icon img")]
                    .flatMap((image) => [...image.classList]);
                  const selected = rowClasses.contains("selected-answer");
                  const correct = feedbackClasses.includes("feedback-correct")
                    || feedbackClasses.includes("feedback-missed")
                    || rowClasses.contains("missed-answer");
                  return {
                    label: text(".number", row).replace(/\.$/, ""),
                    text: text(".answer", row),
                    html: row.querySelector(".answer")?.innerHTML.trim() || "",
                    selected,
                    correct,
                    images: absoluteUrls(".answer img", "src", row),
                  };
                });
                const userAnswerElement = card.querySelector(".user-answer");
                const answerGiven = userAnswerElement ? {
                  text: clean(userAnswerElement.innerText),
                  html: userAnswerElement.innerHTML.trim(),
                  correct: Boolean(userAnswerElement.querySelector(".feedback-correct")),
                  images: absoluteUrls("img:not(.icon)", "src", userAnswerElement),
                } : null;
                const acceptedAnswers = [...card.querySelectorAll(".correct-answers")].map(
                  (answer) => ({
                    text: clean(answer.innerText),
                    html: answer.innerHTML.trim(),
                    images: absoluteUrls("img:not(.icon)", "src", answer),
                  })
                );
                let status = "unknown";
                if (card.querySelector("i.qc")) status = "correct";
                else if (card.querySelector("i.qw")) status = "incorrect";
                else if (card.querySelector("i.qpc")) status = "partially_correct";
                else if (card.querySelector("i.qu")) status = "unanswered";
                return {
                  number: Number(qbox?.dataset.questionNumber || index + 1),
                  question_id: card.id.replace(/^switch-user-q/, ""),
                  text: clean(holder?.innerText || ""),
                  html: holder?.innerHTML.trim() || "",
                  images: holder ? absoluteUrls("img", "src", holder) : [],
                  points_scored: points ? Number(points[1]) : null,
                  points_available: points ? Number(points[2]) : null,
                  status,
                  selected_answers: answers.filter((answer) => answer.selected),
                  correct_answers: answers.filter((answer) => answer.correct),
                  answer_given: answerGiven,
                  accepted_answers: acceptedAnswers,
                  answers,
                };
              });

              return {
                student_name: clean([
                  text("#showText_firstname"),
                  text("#showText_lastname"),
                ].filter(Boolean).join(" ")),
                test_name: text("#result-summary-area .name-wrapper .text"),
                points_scored: numberValue("#pointsscoredspan"),
                points_available: numberValue("#pointsavailablespan"),
                percentage: numberValue("#percent-number"),
                duration: text("#resultsdiv_duration_tt"),
                date_started: text("#resultsdiv_datestarted_tt"),
                date_finished: text("#resultsdiv_datefinished_tt"),
                questions,
              };
            }
            """
        )
        return {"result_url": page.url, "source_row": source_row, **detail}

    @staticmethod
    def _load_checkpoint(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []

    @staticmethod
    def _write_checkpoint(path: Path, records: list[dict[str, Any]]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)


def load_result_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return [row for row in payload if isinstance(row, dict) and row.get("result_link")]
