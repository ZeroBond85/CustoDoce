"""Shared fixtures for e2e tests (local Streamlit at http://localhost:8501)."""

import os

import pytest
from playwright.sync_api import sync_playwright

# Local test configuration
LOCAL_BASE_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501")
LOCAL_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def _login_local(page, password: str) -> None:
    """Faz login no Streamlit local (username + senha).

    O login exige usuario E senha nao-vazios (dashboard/login_page.py);
    a senha e validada contra ADMIN_PASSWORD, o usuario apenas precisa
    ser nao-vazio. Preenchemos "admin" como usuario fixo.
    """
    if not password:
        return
    user_input = page.locator('input[aria-label*="Usuario"], input[placeholder="admin"]').first
    if user_input.count() > 0:
        user_input.fill("admin")
    pwd_input = page.locator('input[type="password"]').first
    if pwd_input.count() > 0:
        pwd_input.fill(password)
        entrar = page.get_by_role("button", name="Entrar", exact=True).first
        if entrar.count() > 0:
            entrar.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)


@pytest.fixture(scope="session")
def browser():
    """Browser instance for e2e tests."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        yield b
        b.close()


@pytest.fixture(scope="session")
def logged_in_app_and_page_local(browser):
    """Returns (app_frame_or_page, page) for tests against local Streamlit server.

    Streamlit local nao usa iframes como no cloud, entao retornamos (page, page).
    Em testes que necessitam de frame, ambos apontam para a mesma page.
    """
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(LOCAL_BASE_URL, timeout=120000)
    page.wait_for_load_state("networkidle")
    _login_local(page, LOCAL_ADMIN_PASSWORD)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector('[data-testid="stSidebar"] a', timeout=60000)
    yield page, page
    page.close()


# NOTE: Nao usar pytest_plugins para importar test_e2e_real.
# Isso criaria conflito de fixtures 'browser' (duas definicoes session scope).
# test_e2e_real.py ja importa seus helpers diretamente.
