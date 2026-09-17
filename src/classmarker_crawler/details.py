from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

from .config import Settings
from .crawler import ClassMarkerCrawler


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
        *,
        retry_errors: bool = False,
    ) -> list[dict[str, Any]]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        completed = self._load_checkpoint(output_path)

        if retry_errors:
            failed_urls = {
                item.get("result_url")
                for item in completed
                if "error" in item or len(item.get("questions", [])) == 0
            }
            existing_urls = {item.get("result_url") for item in completed}
            pending_urls = failed_urls | {
                row.get("result_link")
                for row in result_rows
                if row.get("result_link") not in existing_urls
            }
            pending = [row for row in result_rows if row.get("result_link") in pending_urls]
            print(f"Retry mode: found {len(pending)} test(s) to (re-)crawl.", flush=True)
        else:
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
                total_pending = len(pending)
                for index, row in enumerate(pending, start=1):
                    url = row.get("result_link")
                    if not isinstance(url, str) or not url:
                        continue
                    test_label = row.get("test_title") or row.get("Name") or "Unknown"
                    action_type = row.get("column_5") or ""
                    print(
                        f"\n[{index}/{total_pending}] Crawling: {test_label}"
                        + (f" ({action_type})" if action_type else "")
                        + "...",
                        flush=True,
                    )
                    try:
                        detail = await self._crawl_one(page, url, row)
                    except Exception as exc:  # noqa: BLE001 - Keep checkpoint usable
                        detail = {
                            "result_url": url,
                            "source_row": row,
                            "error": f"{type(exc).__name__}: {exc}",
                            "questions": [],
                        }

                    # Replace in-place if existing, or append
                    existing_index = next(
                        (i for i, item in enumerate(completed) if item.get("result_url") == url),
                        None,
                    )
                    if existing_index is not None:
                        completed[existing_index] = detail
                    else:
                        completed.append(detail)

                    self._write_checkpoint(output_path, completed)
                    print(
                        f"[{index}/{total_pending}] Completed {detail.get('test_name') or test_label}: "
                        f"{len(detail['questions'])} question(s)",
                        flush=True,
                    )
                    await page.wait_for_timeout(int(self.delay * 1000))
            finally:
                try:
                    await context.close()
                except Exception:  # noqa: BLE001, S110
                    pass
                try:
                    await browser.close()
                except Exception:  # noqa: BLE001, S110
                    pass

        return completed

    async def _crawl_one(
        self,
        page: Page,
        url: str,
        source_row: dict[str, Any],
    ) -> dict[str, Any]:
        for attempt in range(3):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                break
            except Exception as exc:
                if attempt == 2:
                    raise
                print(f"   ! Navigation warning ({exc}), retrying attempt {attempt + 2}/3...", flush=True)
                await page.wait_for_timeout(2000)

        is_live = (
            "/test/start/" in url
            or "/test/start/" in page.url
            or "/online-test/start/" in page.url
            or source_row.get("column_5") in ("Start", "Resume")
        )
        if is_live:
            return await self._crawl_live_test(page, url, source_row)
        return await self._crawl_results_page(page, url, source_row)

    async def _crawl_results_page(
        self,
        page: Page,
        url: str,
        source_row: dict[str, Any],
    ) -> dict[str, Any]:
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

    async def _crawl_live_test(
        self,
        page: Page,
        url: str,
        source_row: dict[str, Any],
    ) -> dict[str, Any]:
        if page.url == "about:blank" or not page.url.startswith(url.split("?", 1)[0]):
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        # If there is an introductory screen with a Start or Resume button, click it
        try:
            start_btn = page.locator(
                'button:has-text("Start"), ion-button:has-text("Start"), a:has-text("Start"), '
                'button:has-text("Resume"), ion-button:has-text("Resume"), a:has-text("Resume"), .btn-start'
            ).first
            if (
                await start_btn.count() > 0
                and await start_btn.is_visible()
                and await page.locator(".test-content").count() == 0
            ):
                await start_btn.click()
                await page.wait_for_timeout(1000)
        except Exception:  # noqa: BLE001, S110
            pass

        # Wait for test content or title area to appear
        await page.locator(".test-content, #test-contents, #test-title").first.wait_for(
            state="attached", timeout=30_000
        )
        await page.wait_for_timeout(1000)

        # Extract test name
        test_name = ""
        title_elem = page.locator("#test-title h1, .test-title-area h1, .template-title h1").first
        if await title_elem.count() > 0:
            test_name = (await title_elem.text_content() or "").strip()
        if not test_name:
            test_name = (source_row.get("test_title") or source_row.get("Name") or "").strip()

        # Extract student name
        student_name = ""
        student_elem = page.locator(
            ".test-content-user-name .username-text, #test-title-user-area .username-text, .username-text"
        ).first
        if await student_elem.count() > 0:
            student_name = (await student_elem.text_content() or "").strip()

        # If test was resumed at Question > 1, try going back to Question 1 if allowed
        try:
            prev_btn = page.locator(
                'ion-button.button-prev, ion-button:has-text("Previous"), ion-button:has-text("Back")'
            ).first
            for _ in range(50):
                if await prev_btn.count() == 0 or not await prev_btn.is_visible():
                    break
                classes = (await prev_btn.get_attribute("class") or "").lower()
                disabled = (
                    await prev_btn.get_attribute("disabled")
                    or await prev_btn.get_attribute("aria-disabled")
                )
                if disabled == "true" or "disabled" in classes:
                    break
                card_title = await page.locator("ion-card-title").first.text_content() or ""
                if "Question 1 of" in card_title or "Question 1 " in card_title:
                    break
                await prev_btn.click()
                await page.wait_for_timeout(400)
        except Exception:  # noqa: BLE001, S110
            pass

        # Loop through questions using Next button
        questions: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        max_steps = 200

        for step in range(max_steps):
            try:
                await page.locator(".test-content").first.wait_for(state="visible", timeout=15_000)
            except Exception:  # noqa: BLE001
                break

            q_data = await page.evaluate(
                r"""
                () => {
                  const clean = (value) => (value || "")
                    .replace(/\u00a0/g, " ")
                    .replace(/[ \t]+\n/g, "\n")
                    .replace(/\n{3,}/g, "\n\n")
                    .trim();
                  const absoluteUrls = (selector, attribute, root) =>
                    [...root.querySelectorAll(selector)]
                      .map((element) => element[attribute] || element.getAttribute(attribute))
                      .filter(Boolean);

                  const card = document.querySelector(".test-content");
                  if (!card) return null;

                  const titleEl = card.querySelector("ion-card-title");
                  const titleText = titleEl ? titleEl.innerText : "";
                  const match = titleText.match(/Question\s+(\d+)\s+of\s+(\d+)/i);
                  const qNum = match ? Number(match[1]) : null;
                  const totalQ = match ? Number(match[2]) : null;

                  let questionId = card.id.replace(/^question-/, "");
                  if (!questionId && card.dataset.cy) {
                    questionId = card.dataset.cy;
                  }

                  const textEl = card.querySelector(".question-text .bbcode") || card.querySelector(".question-text");
                  const textContent = clean(textEl ? textEl.innerText : "");
                  const htmlContent = textEl ? textEl.innerHTML.trim() : "";
                  const images = textEl ? absoluteUrls("img", "src", textEl) : [];

                  const answerItems = [
                    ...card.querySelectorAll(
                      "ion-item.radio-options-area, ion-item.checkbox-options-area, ion-item:has(ion-radio), ion-item:has(ion-checkbox)"
                    )
                  ];
                  const answers = answerItems.map((item, idx) => {
                    const indexEl = item.querySelector(".question-index");
                    const label = clean(indexEl ? indexEl.innerText : "").replace(/\.$/, "") || String.fromCharCode(65 + idx);
                    const contentEl = item.querySelector(".question-content .bbcode")
                      || item.querySelector(".question-content [data-cy='question-option-text']")
                      || item.querySelector(".question-content");
                    const optText = clean(contentEl ? contentEl.innerText : "");
                    const optHtml = contentEl ? contentEl.innerHTML.trim() : "";
                    const optImages = contentEl ? absoluteUrls("img", "src", contentEl) : [];

                    const radio = item.querySelector("ion-radio, ion-checkbox");
                    const selected = radio ? (
                      radio.getAttribute("aria-checked") === "true"
                      || radio.getAttribute("checked") === "true"
                      || radio.checked === true
                    ) : false;

                    return {
                      label,
                      text: optText,
                      html: optHtml,
                      selected,
                      correct: false,
                      images: optImages,
                    };
                  });

                  let answerGiven = null;
                  if (answers.length === 0) {
                    const inputEl = card.querySelector("ion-input input, input[type='text'], textarea");
                    if (inputEl && inputEl.value) {
                      answerGiven = {
                        text: clean(inputEl.value),
                        html: clean(inputEl.value),
                        correct: false,
                        images: [],
                      };
                    }
                  }

                  return {
                    number: qNum,
                    total_questions: totalQ,
                    question_id: questionId,
                    text: textContent,
                    html: htmlContent,
                    images,
                    points_scored: null,
                    points_available: null,
                    status: "unanswered",
                    selected_answers: answers.filter((a) => a.selected),
                    correct_answers: [],
                    answer_given: answerGiven,
                    accepted_answers: [],
                    answers,
                  };
                }
                """
            )

            if not q_data:
                break

            total_q = q_data.pop("total_questions", None)
            q_id = q_data.get("question_id") or f"q_{step+1}"

            if q_id not in seen_ids:
                seen_ids.add(q_id)
                if not q_data.get("number"):
                    q_data["number"] = len(questions) + 1
                questions.append(q_data)

            q_num_display = q_data.get("number")
            total_display = total_q or "?"
            print(f"   -> Question {q_num_display}/{total_display} (ID: {q_id})", flush=True)

            curr_num = q_data.get("number") or (step + 1)
            is_last = False
            if total_q and curr_num >= total_q:
                is_last = True

            next_btn = page.locator(
                'ion-button.button-next, ion-button[data-cy="continue-btn"], ion-button:has-text("Next")'
            ).first

            if not is_last:
                if await next_btn.count() == 0 or not await next_btn.is_visible():
                    is_last = True
                else:
                    try:
                        btn_text = (await next_btn.text_content(timeout=3000) or "").strip().lower()
                    except Exception:  # noqa: BLE001
                        btn_text = ""
                    classes = (await next_btn.get_attribute("class") or "").lower()
                    disabled = (
                        await next_btn.get_attribute("disabled")
                        or await next_btn.get_attribute("aria-disabled")
                    )
                    if (
                        disabled == "true"
                        or "disabled" in classes
                        or not any(w in btn_text for w in ("next", "tiếp"))
                    ):
                        is_last = True

            if is_last:
                # Do NOT submit the exam. Save and finish later.
                save_btn = page.locator(
                    'ion-button.resume-later-button, ion-button:has-text("Save and finish later")'
                ).first
                if await save_btn.count() > 0 and await save_btn.is_visible():
                    try:
                        await save_btn.click(timeout=5000)
                        await page.wait_for_timeout(1000)
                    except Exception:  # noqa: BLE001, S110
                        pass
                break

            # Dismiss any blocking modal/alert if present
            modal_close = page.locator(
                "ion-modal.global-error-modal ion-button, ion-alert button, .alert-button, .global-error-modal button"
            ).first
            if await modal_close.count() > 0 and await modal_close.is_visible():
                try:
                    await modal_close.click(timeout=2000)
                    await page.wait_for_timeout(500)
                except Exception:  # noqa: BLE001, S110
                    pass

            # Click next question
            prev_id = q_id
            try:
                await next_btn.click(timeout=6000)
            except Exception:  # noqa: BLE001
                try:
                    await next_btn.click(force=True, timeout=3000)
                except Exception:  # noqa: BLE001, S110
                    pass
            await page.wait_for_timeout(1000)

            # ClassMarker shows 'No answer given' warning on first click; second click confirms skipping
            card_now = page.locator(".test-content").first
            now_id = (await card_now.get_attribute("id") or "").replace("question-", "")
            if now_id == prev_id and await next_btn.count() > 0 and await next_btn.is_visible():
                try:
                    btn_text = (await next_btn.text_content(timeout=3000) or "").strip().lower()
                except Exception:  # noqa: BLE001
                    btn_text = ""
                if any(w in btn_text for w in ("next", "tiếp")):
                    try:
                        await next_btn.click(timeout=5000)
                    except Exception:  # noqa: BLE001
                        try:
                            await next_btn.click(force=True, timeout=3000)
                        except Exception:  # noqa: BLE001, S110
                            pass
                    await page.wait_for_timeout(1500)

            try:
                await page.wait_for_function(
                    f"""() => {{
                        const el = document.querySelector('.test-content');
                        return el && el.id !== 'question-{prev_id}' && el.id !== '{prev_id}';
                    }}""",
                    timeout=8_000,
                )
            except Exception:  # noqa: BLE001
                await page.wait_for_timeout(1000)

            await page.wait_for_timeout(int(self.delay * 1000))

        print(f"   ✓ Finished live test: {len(questions)} question(s) collected.", flush=True)

        return {
            "result_url": url,
            "source_row": source_row,
            "student_name": student_name,
            "test_name": test_name,
            "points_scored": None,
            "points_available": None,
            "percentage": None,
            "duration": "-",
            "date_started": "-",
            "date_finished": "-",
            "questions": questions,
        }

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
        raise TypeError(f"Expected a JSON list in {path}")
    return [row for row in payload if isinstance(row, dict) and row.get("result_link")]
