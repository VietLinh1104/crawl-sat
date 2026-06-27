from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    username: str | None
    password: str | None
    target_url: str
    username_selector: str
    password_selector: str
    submit_selector: str
    table_selector: str
    next_selector: str
    auth_state: Path = Path("playwright/.auth/state.json")

    @classmethod
    def from_env(cls, target_url: str | None = None) -> "Settings":
        load_dotenv()
        url = target_url or os.getenv("CLASSMARKER_TARGET_URL", "")
        if not url.startswith(("https://www.classmarker.com/", "https://classmarker.com/")):
            raise ValueError("Target URL must be an HTTPS ClassMarker URL")
        return cls(
            username=os.getenv("CLASSMARKER_USERNAME"),
            password=os.getenv("CLASSMARKER_PASSWORD"),
            target_url=url,
            username_selector=os.getenv(
                "CLASSMARKER_USERNAME_SELECTOR",
                'input[type="email"], input[name="email"], input[name="username"]',
            ),
            password_selector=os.getenv(
                "CLASSMARKER_PASSWORD_SELECTOR", 'input[type="password"]'
            ),
            submit_selector=os.getenv(
                "CLASSMARKER_SUBMIT_SELECTOR", 'button[type="submit"], input[type="submit"]'
            ),
            table_selector=os.getenv("CLASSMARKER_TABLE_SELECTOR", "table"),
            next_selector=os.getenv(
                "CLASSMARKER_NEXT_SELECTOR", 'a[rel="next"], a:has-text("Next"), a:has-text("›")'
            ),
        )

