"""E2E smoke ultra-fast: verifica apenas que Streamlit responde e o login form renderiza.

NAO depende de:
- st.navigation() renderizar em headless (long-standing issue, Licao #29)
- Click em Entrar funcionar via WebSocket em localhost
- Sidebar/navigation contents

Verifica apenas:
- Servidor responde HTTP 200 em /
- Login form e password input renderizam
- Tela nao tem excecoes Streamlit/Python visíveis

Roda em ~10s. Nao bloqueia PR mas falha se algo fundamental quebrar.
"""
import os
import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def get_app(page):
    for f in page.frames:
        if "/~/+" in f.url:
            return f
    return page


ERROR_SELECTORS = [
    ".stException",
    "text=StreamlitAPIException",
    "text=Traceback",
    "text=st.error",
]


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        yield b
        b.close()


def _load_and_assert_no_errors(page, context):
    """Confirma que a pagina carrega sem erros visíveis."""
    for sel in ERROR_SELECTORS:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                txt = (el.text_content() or "")[:200]
                pytest.fail(f"{context} erro: '{txt}'")
        except Exception:
            pass


def _wait_script_running(page, timeout_ms=60000):
    """Espera ate a pagina entrar em script-state=running. Tolerante a 'notRunning' persistente."""
    import time
    start = time.time()
    saw_running = False
    while (time.time() - start) * 1000 < timeout_ms:
        try:
            states = []
            for el in page.locator("[data-test-script-state]").all():
                s = el.get_attribute("data-test-script-state")
                if s:
                    states.append(s)
            if "running" in states:
                saw_running = True
                return True
        except Exception:
            pass
        time.sleep(1)
    return saw_running


def test_server_responds(browser):
    """Servidor responde HTTP 200 na raiz."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    response = page.goto(BASE_URL, timeout=60000)
    assert response is not None and response.status == 200, (
        f"Streamlit nao respondeu 200 em {BASE_URL}: "
        f"status={response.status if response else 'no response'}"
    )
    page.close()


def test_login_form_renders(browser):
    """Login form renderiza apos o boot do script Streamlit."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_load_state("domcontentloaded")

    # Streamlit pode levar 10-20s para bootar e renderizar login form
    pwd_count = 0
    entrar_count = 0
    for _ in range(45):  # ate 45s
        page.wait_for_timeout(1000)
        try:
            pwd_count = page.locator("input[type='password']").count()
            entrar_count = page.get_by_role("button", name="Entrar", exact=True).count()
            if pwd_count > 0 and entrar_count > 0:
                break
        except Exception:
            pass

    assert pwd_count > 0, "Campo de senha nao renderizou (45s)"
    assert entrar_count > 0, "Botao 'Entrar' nao encontrado (45s)"
    _load_and_assert_no_errors(page, "login_form_renders")
    page.close()


def test_login_submit_completes_without_exception(browser):
    """Submeter credenciais nao causa excecao Streamlit (clicando em Entrar).

    NAO verifica sidebar/navigation render (Licao #29 — flaky em headless).
    Apenas garante que o submit limpa o ciclo sem erro fatal.
    """
    if not ADMIN_PASSWORD:
        pytest.skip("ADMIN_PASSWORD nao definido no env")

    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_load_state("domcontentloaded")

    # Esperar pelo login form
    pwd = page.locator("input[type='password']").first
    pwd.wait_for(state="visible", timeout=60000)

    user_input = page.locator("input[type='text']").first
    user_input.fill("admin")
    pwd.fill(ADMIN_PASSWORD)

    entrar = page.get_by_role("button", name="Entrar", exact=True).first
    entrar.wait_for(state="visible", timeout=5000)
    entrar.click()

    # Esperar 8s para o ciclo de rerun completar; nao exigimos sidebar
    page.wait_for_timeout(8000)

    # Apenas verifica: o session_id conecta E nao ha excecao fatal visivel
    cstate = page.locator("[data-test-connection-state]").first
    if cstate.count() > 0:
        cs = cstate.get_attribute("data-test-connection-state")
        assert cs == "CONNECTED", f"WebSocket desconectado: state={cs}"

    _load_and_assert_no_errors(page, "login_submit")
    page.close()
