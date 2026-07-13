"""
Shared Playwright fixtures for the tests/ suite, which runs against the
live public site https://www.saucedemo.com in CI (see agents/tools.py's
run_playwright_suite). There's no staging environment to fall back on, so
this file exists to make that suite tolerate real-world flakiness instead
of assuming a local, deterministic target:

- `base_url` lets tests use relative `page.goto("/")` calls instead of
  repeating the hostname, and is the single place to point the suite
  elsewhere (e.g. a local mock) if that's ever needed.
- A shorter default action/navigation timeout than Playwright's 30s
  default means a genuinely broken selector fails fast instead of
  padding every red run by up to 30s per assertion.
"""

import pytest
from playwright.sync_api import Page

BASE_URL = "https://www.saucedemo.com"
DEFAULT_TIMEOUT_MS = 15_000


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(autouse=True)
def _default_timeouts(page: Page) -> None:
    page.set_default_timeout(DEFAULT_TIMEOUT_MS)
    page.set_default_navigation_timeout(DEFAULT_TIMEOUT_MS)
