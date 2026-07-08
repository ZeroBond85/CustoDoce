"""Local E2E fixtures for tests running against local Streamlit server."""

import os
from playwright.sync_api import sync_playwright
import pytest

# Use local Streamlit server
LOCAL_BASE_URL = "http://localhost:8501"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def login_to_app(page, password: str = ""):
    """Login to the Streamlit app."""
    page.goto(LOCAL_BASE_URL, timeout=120000)

    # Check if login form is present
    password_input = page.locator('input[type="password"]')
    if password_input.count() > 0:
        password_input.first.fill(password)
        submit_btn = page.locator('button:has-text("Entrar"), button:has-text("Login"), button[type="submit"]').first
        submit_btn.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)


@pytest.fixture(scope="session")
def browser():
    """Create a browser instance for the test session."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        yield b
        b.close()


@pytest.fixture(scope="session")
def logged_in_app_and_page_local(browser):
    """Returns (app, page) for tests against local Streamlit server."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(LOCAL_BASE_URL, timeout=120000)
    login_to_app(page, ADMIN_PASSWORD)

    # Get the app frame
    app = None
    for f in page.frames:
        if "/~/+" in f.url:
            app = f
            break
    if app is None:
        app = page

    yield app, page
    page.close()


@pytest.fixture
def logged_in_app_local(browser):
    """Returns app frame only for tests that don't need page."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(LOCAL_BASE_URL, timeout=120000)
    login_to_app(page, ADMIN_PASSWORD)

    app = None
    for f in page.frames:
        if "/~/+" in f.url:
            app = f
            break
    if app is None:
        app = page

    yield app
    page.close()
