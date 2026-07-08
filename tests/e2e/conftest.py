"""Shared fixtures for e2e tests (local Streamlit at http://localhost:8501)."""

import os

import pytest
from playwright.sync_api import sync_playwright

# Local test configuration
LOCAL_BASE_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501")
LOCAL_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def _get_app_frame(page):
    """Return the Streamlit app frame; fallback to page if not in iframe."""
    for f in page.frames:
        if "/~/+" in f.url:
            return f
    return page


@pytest.fixture(scope="session")
def browser():
    """Browser instance for e2e tests."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        yield b
        b.close()


@pytest.fixture(scope="session")
def logged_in_app_and_page_local(browser):
    """Returns (app, page) for tests against local Streamlit server."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(LOCAL_BASE_URL, timeout=120000)

    # Login if password provided
    if LOCAL_ADMIN_PASSWORD:
        password_input = page.locator('input[type="password"]')
        if password_input.count() > 0:
            password_input.fill(LOCAL_ADMIN_PASSWORD)
            page.locator('button:has-text("Entrar")').first.click()
            page.wait_for_timeout(3000)

    yield _get_app_frame(page), page
    page.close()


# Import cloud fixtures from test_e2e_real for cloud tests
pytest_plugins = ["tests.e2e.test_e2e_real"]
