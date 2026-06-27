from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import BrowserContext, Page, async_playwright

from .config import Settings


@dataclass
class CrawlResult:
    source_url: str
    pages: list[dict[str, Any]]


class ClassMarkerCrawler:
    def __init__(
        self,
        settings: Settings,
        *,
        headed: bool = False,
        manual_login: bool = False,
        delay: float = 1.0,
        max_pages: int = 20,
    ) -> None:
        self.settings = settings
        self.headed = headed
        self.manual_login = manual_login
        self.delay = max(delay, 0.25)
        self.max_pages = max(1, max_pages)

    async def run(self) -> CrawlResult:
        self.settings.auth_state.parent.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=not self.headed)
            context_args: dict[str, Any] = {}
            if self.settings.auth_state.exists():
                context_args["storage_state"] = str(self.settings.auth_state)
            context = await browser.new_context(**context_args)
            try:
                page = await context.new_page()
                await self._open_target(page, context)
                pages = await self._crawl_pages(page)
                return CrawlResult(source_url=self.settings.target_url, pages=pages)
            finally:
                await context.close()
                await browser.close()

    async def _open_target(self, page: Page, context: BrowserContext) -> None:
        await page.goto(self.settings.target_url, wait_until="domcontentloaded")
        if await self._looks_like_login(page):
            await self._login(page)
            await context.storage_state(path=str(self.settings.auth_state))
            await page.goto(self.settings.target_url, wait_until="domcontentloaded")

        if await self._looks_like_login(page):
            raise RuntimeError("Login did not succeed; run with --manual-login --headed")

    async def _looks_like_login(self, page: Page) -> bool:
        password = page.locator(self.settings.password_selector).first
        return await password.count() > 0 and await password.is_visible()

    async def _login(self, page: Page) -> None:
        if self.manual_login:
            if not self.headed:
                raise ValueError("--manual-login requires --headed")
            print("Complete login/2FA in the browser, then press Enter here...")
            await asyncio.to_thread(input)
            await page.wait_for_load_state("domcontentloaded")
            return

        if not self.settings.username or not self.settings.password:
            raise ValueError("Set CLASSMARKER_USERNAME and CLASSMARKER_PASSWORD in .env")

        await page.locator(self.settings.username_selector).first.fill(self.settings.username)
        await page.locator(self.settings.password_selector).first.fill(self.settings.password)
        await page.locator(self.settings.submit_selector).first.click()
        await page.wait_for_load_state("domcontentloaded")

    async def _crawl_pages(self, page: Page) -> list[dict[str, Any]]:
        crawled: list[dict[str, Any]] = []
        visited: set[str] = set()

        for page_number in range(1, self.max_pages + 1):
            if page.url in visited:
                break
            visited.add(page.url)
            await page.wait_for_timeout(int(self.delay * 1000))
            tables = await self._extract_tables(page)
            crawled.append({"page": page_number, "url": page.url, "tables": tables})

            next_link = page.locator(self.settings.next_selector).first
            if await next_link.count() == 0 or not await next_link.is_visible():
                break
            aria_disabled = await next_link.get_attribute("aria-disabled")
            classes = (await next_link.get_attribute("class") or "").lower()
            if aria_disabled == "true" or "disabled" in classes:
                break
            await next_link.click()
            await page.wait_for_load_state("domcontentloaded")

        return crawled

    async def _extract_tables(self, page: Page) -> list[dict[str, Any]]:
        tables = page.locator(self.settings.table_selector)
        output: list[dict[str, Any]] = []
        for index in range(await tables.count()):
            table = tables.nth(index)
            headers = [self._clean(x) for x in await table.locator("thead th").all_text_contents()]
            rows = table.locator("tbody tr")
            if await rows.count() == 0:
                rows = table.locator("tr")

            data: list[dict[str, str]] = []
            for row_index in range(await rows.count()):
                row = rows.nth(row_index)
                cells = [self._clean(x) for x in await row.locator("th, td").all_text_contents()]
                if not cells or (not headers and row_index == 0):
                    if not headers:
                        headers = cells
                    continue
                names = headers or [f"column_{i + 1}" for i in range(len(cells))]
                names = self._unique_headers(names, len(cells))
                record = dict(zip(names, cells, strict=False))
                if record.get("column_5") == "Results":
                    result_link = row.locator('a.btn-results, a:has-text("Results")').first
                    if await result_link.count() > 0:
                        href = await result_link.get_attribute("href")
                        if href:
                            record["result_link"] = urljoin(page.url, href)
                data.append(record)
            output.append({"index": index, "headers": headers, "rows": data})
        return output

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _unique_headers(headers: list[str], cell_count: int) -> list[str]:
        result: list[str] = []
        counts: dict[str, int] = {}
        for index in range(cell_count):
            base = headers[index] if index < len(headers) and headers[index] else f"column_{index + 1}"
            counts[base] = counts.get(base, 0) + 1
            result.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
        return result
