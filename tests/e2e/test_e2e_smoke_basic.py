"""E2E smoke: login + page crawl de todas as 19 paginas do dashboard.

Fluxo:
- Servidor responde HTTP 200 em /
- Login form renderiza com password input
- Submeter credenciais completa sem excecao
- Sidebar navigation renderiza (todas as 19 paginas)
- Crawl de cada pagina via click no nav link:

Testes sao independentes. Cada um abre/fecha a propria pagina.

O crawl de 19 paginas leva ~3-4min (com screenshot).
"""

import os
import sys
from pathlib import Path

import pytest

_repo_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _repo_root)

from dashboard.navigation_config import MENU_GROUPS

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
        f"Streamlit nao respondeu 200 em {BASE_URL}: status={response.status if response else 'no response'}"
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
    for _ in range(30):  # ate 30s
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

    # Esperar para o ciclo de rerun completar; nao exigimos sidebar
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)

    # Apenas verifica: o session_id conecta E nao ha excecao fatal visivel
    cstate = page.locator("[data-test-connection-state]").first
    if cstate.count() > 0:
        cs = cstate.get_attribute("data-test-connection-state")
        assert cs == "CONNECTED", f"WebSocket desconectado: state={cs}"

    _load_and_assert_no_errors(page, "login_submit")
    page.close()


# ── Page crawl: navega por todas as paginas do MENU_GROUPS ──
# Single source of truth: derive from MENU_GROUPS (auto-adapta-se a mudancas)
_EXPECTED_TEXT_OVERRIDES: dict[str, str] = {
    "visao_geral": "Total Preços",
    "fontes": "Fontes",
    "scrapers": "Scrapers",
    "scraper_health": "Health",
}

def _build_pages_to_crawl() -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    for _group_label, group_pages in MENU_GROUPS.items():
        for nav_label, _icon, page_id in group_pages:
            expected = _EXPECTED_TEXT_OVERRIDES.get(page_id, nav_label)
            result.append((nav_label, page_id, expected))
    return result

PAGES_TO_CRAWL = _build_pages_to_crawl()


def _wait_page_stable(page, timeout_s=15):
    """Aguarda a pagina atual estabilizar (rede idle + script running) para
    garantir que o handler de click do st.navigation estaja ativo.

    Licao #50: apos o render de uma pagina pesada (ex.: Revisao com
    fila real + imagens externas), o handler de nav fica dessincronizado
    por uma janela que, com dados reais, pode durar >20s. Clicar durante
    essa janela vira no-op. Esperar networkidle (sem requisicoes de rede
    pendentes) e o script-state 'running' garante que o handler voltou.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_s * 1000)
    except Exception:
        pass
    try:
        page.wait_for_function(
            "() => { const el = document.querySelector('[data-test-script-state]');"
            " return !el || el.getAttribute('data-test-script-state') === 'running'; }",
            timeout=timeout_s * 1000,
        )
    except Exception:
        pass


def _click_nav_until_url(page, sidebar, nav_text, expected_path, max_attempts=3, per_wait_ms=5000):
    """Clica no nav link real e aguarda a URL mudar, re-clicando apos a
    pagina estabilizar. Mantem a sessao SPA (nao faz reload completo)
    para preservar o login em st.session_state. Retorna True se a URL
    passou a conter expected_path.
    """
    target_glob = f"**/{expected_path}**"
    for _ in range(max_attempts):
        _wait_page_stable(page, timeout_s=12)
        link = sidebar.locator("a").filter(has_text=nav_text).first
        if link.count() == 0:
            return False
        link.click()
        try:
            page.wait_for_url(target_glob, timeout=per_wait_ms)
            return True
        except Exception as exc:  # noqa: BLE001 - handler de nav pode falhar temporariamente
            _ = exc
            continue
    return False


def test_all_pages_crawl(browser):
    """Login + crawl todas as 19 paginas via sidebar nav. Screenshots + deteccao de erro."""
    if not ADMIN_PASSWORD:
        pytest.skip("ADMIN_PASSWORD nao definido no env")

    page = browser.new_page(viewport={"width": 1280, "height": 800})
    failures: list[str] = []
    screenshots_dir = Path(os.path.dirname(__file__)) / "e2e_screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    try:
        # ── Login ──
        page.goto(BASE_URL, timeout=60000)
        page.wait_for_load_state("domcontentloaded")

        pwd = page.locator("input[type='password']").first
        pwd.wait_for(state="visible", timeout=60000)
        user_input = page.locator("input[type='text']").first
        user_input.fill("admin")
        pwd.fill(ADMIN_PASSWORD)
        entrar = page.get_by_role("button", name="Entrar", exact=True).first
        entrar.wait_for(state="visible", timeout=5000)
        entrar.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # ── Verificar sidebar ──
        sidebar = page.locator('[data-testid="stSidebar"]')
        if sidebar.count() == 0:
            pytest.fail("Sidebar nao renderizou apos login (60s)")

        # ── Crawl cada pagina ──
        for nav_text, expected_path, expected_text in PAGES_TO_CRAWL:
            try:
                # visao_geral é a página default (URL "/") — já carregada
                if expected_path == "visao_geral":
                    pass
                else:
                    # Clicar no nav link (cobertura de navegacao real SPA).
                    # Licao #N: apos o render de uma pagina pesada (ex.: Revisao),
                    # o handler de click do st.navigation do Streamlit fica dessincronizado
                    # por uma janela de alguns segundos — os primeiros cliques viram
                    # no-op (URL nao muda) ate o handler reativar. Por isso pollamos
                    # a URL e re-clicamos (ate 8 tentativas) em vez de checar 1x.
                    navigated = _click_nav_until_url(
                        page, sidebar, nav_text, expected_path
                    )
                    if not navigated:
                        failures.append(
                            f"[{nav_text}] Falha ao navegar (URL={page.url})"
                        )
                        continue
                    _wait_page_stable(page, timeout_s=12)

                # Screenshot
                safe_name = nav_text.replace(" ", "_").replace("/", "_").replace("&", "e")[:40]
                page.screenshot(path=str(screenshots_dir / f"{safe_name}.png"))

                # Verificar estado
                state = page.locator("[data-test-script-state]").first.get_attribute("data-test-script-state")
                if state == "notRunning":
                    # Verificar se ha erro visivel
                    _load_and_assert_no_errors(page, f"page_{safe_name}")

                # Verificar URL contem path esperado
                # visao_geral é a página default — URL fica "/"
                if expected_path != "visao_geral" and expected_path not in page.url:
                    failures.append(f"[{nav_text}] URL nao contem '{expected_path}': {page.url}")

                # Verificar texto esperado no body
                body_text = page.locator("body").inner_text()
                if expected_text not in body_text:
                    failures.append(f"[{nav_text}] Texto '{expected_text}' nao encontrado")

            except Exception as exc:
                failures.append(f"[{nav_text}] Excecao: {exc}")

        if failures:
            pytest.fail("Falhas no crawl:\n" + "\n".join(failures))

    finally:
        page.close()
