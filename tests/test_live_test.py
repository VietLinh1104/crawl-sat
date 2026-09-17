from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from classmarker_crawler.config import Settings
from classmarker_crawler.details import ResultDetailsCrawler

HTML_SAMPLE = """<!DOCTYPE html>
<html>
<head><title>Test Live</title></head>
<body>
<div class="template">
  <div id="test-contents">
    <div class="template-title">
      <div id="test-title"><h1>Advanced Common Sense Practice 31</h1></div>
    </div>
    <div id="test-title-user-area" class="partial-info">
      <span class="username test-content-user-name">
        <span class="username-text">Pham Hoang Son D15</span>
      </span>
    </div>
    <div id="test-content-wrapper">
      <div class="test-content" id="question-36500180" data-cy="question-idx-1">
        <ion-card class="test__card">
          <ion-card-header>
            <ion-card-title>Question 1 of 2</ion-card-title>
          </ion-card-header>
          <ion-card-content>
            <div class="question-text">
              <div class="bbcode">It is proposed to allow the sale of medication.</div>
            </div>
            <ion-radio-group>
              <ion-item class="radio-options-area">
                <ion-radio aria-checked="false"></ion-radio>
                <div class="question-index">A.</div>
                <div class="question-content"><div class="bbcode">Option A text</div></div>
              </ion-item>
              <ion-item class="radio-options-area">
                <ion-radio aria-checked="true"></ion-radio>
                <div class="question-index">B.</div>
                <div class="question-content"><div class="bbcode">Option B text</div></div>
              </ion-item>
            </ion-radio-group>
          </ion-card-content>
        </ion-card>
      </div>
    </div>
    <div class="button-area">
      <ion-button class="button-next" data-cy="continue-btn" onclick="nextQuestion()">Next</ion-button>
      <ion-button class="resume-later-button" onclick="saveLater()">Save and finish later</ion-button>
    </div>
  </div>
</div>

<script>
let current = 1;
function nextQuestion() {
  current = 2;
  const container = document.getElementById('question-36500180');
  container.id = 'question-36500181';
  container.setAttribute('data-cy', 'question-idx-2');
  container.querySelector('ion-card-title').innerText = 'Question 2 of 2';
  container.querySelector('.question-text .bbcode').innerText = 'Question 2 text here';
  
  const options = container.querySelectorAll('.radio-options-area');
  options[0].querySelector('.question-content .bbcode').innerText = 'Q2 Option A';
  options[1].querySelector('.question-content .bbcode').innerText = 'Q2 Option B';

  const nextBtn = document.querySelector('.button-next');
  nextBtn.innerText = 'Submit';
  nextBtn.disabled = true;
}
function saveLater() {
  window.savedLater = true;
}
</script>
</body>
</html>
"""


def test_crawl_live_test_ionic(tmp_path: Path):
    async def _run():
        html_file = tmp_path / "live_test.html"
        html_file.write_text(HTML_SAMPLE, encoding="utf-8")
        url = f"file://{html_file.resolve()}"

        settings = Settings(
            username="test",
            password="test",
            target_url=url,
            username_selector="input",
            password_selector="input",
            submit_selector="button",
            table_selector="table",
            next_selector="a",
            auth_state=tmp_path / "auth.json",
        )

        crawler = ResultDetailsCrawler(settings, delay=0.1)

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)
            source_row = {
                "Name": "Advanced Common Sense Practice 31",
                "column_5": "Start",
                "result_link": url,
            }

            result = await crawler._crawl_one(page, url, source_row)
            await browser.close()

            assert result["test_name"] == "Advanced Common Sense Practice 31"
            assert result["student_name"] == "Pham Hoang Son D15"
            assert len(result["questions"]) == 2

            q1 = result["questions"][0]
            assert q1["number"] == 1
            assert q1["question_id"] == "36500180"
            assert "sale of medication" in q1["text"]
            assert len(q1["answers"]) == 2
            assert q1["answers"][0]["label"] == "A"
            assert q1["answers"][0]["selected"] is False
            assert q1["answers"][1]["label"] == "B"
            assert q1["answers"][1]["selected"] is True

            q2 = result["questions"][1]
            assert q2["number"] == 2
            assert q2["question_id"] == "36500181"
            assert "Question 2 text" in q2["text"]

    asyncio.run(_run())
