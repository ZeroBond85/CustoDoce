"""
E2E Real contra Streamlit Cloud produção.
Testa 16 abas + interações + varre erros.
Lida com frames e login do Streamlit Cloud.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("STREAMLIT_URL", "https://custodoce.streamlit.app")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "custodoce123")

# (page_id, label, expected_text)
PAGES = [
    ("visao_geral", "Visao Geral", "Total"),
    ("precos", "Precos", "Precos"),
    ("historico", "Historico", "Historico"),
    ("flyers", "Flyers", "Flyers"),
    ("revisao", "Revisao", "Revisao"),
    ("fontes", "Fontes & Ofertas", "Fontes"),
    ("ranking", "Ranking", "Ranking"),
    ("insights", "Insights", "Insights"),
    ("lojas", "Lojas", "Lojas"),
    ("ingredientes", "Ingredientes", "Ingredientes"),
    ("alertas", "Alertas", "Alertas"),
    ("scrapers", "Scrapers", "Scrapers"),
    ("relatorios", "Relatorios", "Relatorios"),
    ("config", "Configuracao", "Configuracao"),
    ("calculadora", "Calculadora", "Calculadora"),
    ("diagnostico", "Diagnostico", "Diagnostico"),
]


def get_app(page):
    """Retorna o frame da aplicação Streamlit (após carregar)."""
    for f in page.frames:
        if "/~/+" in f.url:
            return f
    return page


def wake_if_sleeping(page, app):
    """Streamlit Cloud hiberna apos ~60s idle. Detecta o dialog 'gone to sleep'
    e acorda o app cliccando no botao 'Yes, get this app back up!'.
    Retorna app frame atualizado."""
    sleep_dialog = app.locator("text=gone to sleep")
    if sleep_dialog.count() > 0 and sleep_dialog.first.is_visible():
        wake_btn = app.locator("button:has-text('Yes, get this app back up')")
        if wake_btn.count() > 0:
            wake_btn.first.click()
            page.wait_for_timeout(8000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)
            return get_app(page)
    return app


def ensure_app_ready(page, app):
    """Garante que o app esta acordado + sidebar renderizada.
    Reutilizavel antes de cada teste."""
    app = wake_if_sleeping(page, app)
    # Esperar sidebar renderizar (ex: visivel primeiro item)
    try:
        app.locator("button:has-text('Visao Geral')").first.wait_for(state="visible", timeout=15000)
    except Exception:
        pass
    return app


def login_to_app(page):
    """Faz login completo no Streamlit Cloud + dashboard."""
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000)
    app = get_app(page)

    # Streamlit Cloud pode hibernar entre testes -> acordar se necessario
    app = wake_if_sleeping(page, app)

    # Streamlit Cloud password gate (if present)
    pw_input = app.locator("input[type='password']")
    if pw_input.count() > 0:
        pw_input.first.fill(ADMIN_PASSWORD)
        entrar = app.locator("button:has-text('Entrar')")
        if entrar.count() > 0:
            entrar.first.click()
            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)
            app = get_app(page)

    # Dashboard password gate (if present)
    pw_input2 = app.locator("input[type='password']")
    if pw_input2.count() > 0:
        pw_input2.first.fill(ADMIN_PASSWORD)
        entrar2 = app.locator("button:has-text('Entrar')")
        if entrar2.count() > 0:
            entrar2.first.click()
            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)
            app = get_app(page)

    return app


def check_for_errors(app, context="", take_screenshot=True, page=None):
    """Varre página por erros Streamlit/Python."""
    error_selectors = [
        ".stAlert",
        ".stException",
        "text=st.error",
        "text=st.exception",
        "text=Traceback",
        "text=traceback",
        "text=column",
        "text=does not exist",
        "text=DatabaseError",
        "text=OperationalError",
        "text=42P10",
        "text=23505",
        "text=22P02",
        "text=Error:",
        "text=Erro:",
    ]
    for sel in error_selectors:
        try:
            el = app.locator(sel).first
            if el.count() > 0 and el.is_visible():
                text = el.text_content()[:200] if el.text_content() else ""
                if take_screenshot and page:
                    report_dir = Path("data/regression_screenshots")
                    report_dir.mkdir(parents=True, exist_ok=True)
                    ts = os.urandom(4).hex()
                    path = report_dir / f"error_{context}_{ts}.png"
                    with open(path, "wb") as f:
                        f.write(page.screenshot())
                pytest.fail(f"Erro em '{context}': '{text}'")
        except Exception:
            pass


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        yield b
        b.close()


@pytest.fixture
def logged_in_app(browser):
    """Retorna app frame logado no dashboard."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE_URL, timeout=120000)
    app = login_to_app(page)
    yield app
    page.close()


@pytest.fixture
def logged_in_app_and_page(browser):
    """Retorna (app, page) para testes que precisam acordar Streamlit Cloud
    ou tirar screenshots."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE_URL, timeout=120000)
    app = login_to_app(page)
    yield app, page
    page.close()


class TestE2EReal:
    """D1 — Playwright E2E contra Streamlit Cloud"""

    def test_home_mobile(self):
        """Home carrega em viewport mobile (320px)"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 320, "height": 568})
            page.goto(BASE_URL, timeout=120000)
            app = login_to_app(page)
            check_for_errors(app, "home_mobile", page=page)
            browser.close()

    def test_home_tablet(self):
        """Home carrega em viewport tablet (768px)"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 768, "height": 1024})
            page.goto(BASE_URL, timeout=120000)
            app = login_to_app(page)
            check_for_errors(app, "home_tablet", page=page)
            browser.close()

    def test_home_desktop(self):
        """Home carrega em viewport desktop (1280px)"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(BASE_URL, timeout=120000)
            app = login_to_app(page)
            check_for_errors(app, "home_desktop", page=page)
            browser.close()

    @pytest.mark.parametrize("page_id,label,expected", PAGES)
    def test_tab_navigates_without_error(self, logged_in_app_and_page, page_id, label, expected):
        """Cada aba navega sem erro."""
        app, page = logged_in_app_and_page
        # Acordar Streamlit Cloud caso tenha hibernado entre tests
        app = wake_if_sleeping(page, app)
        # Esperar botao com timeout reduzido para fail-fast (default 30s)
        btn = app.locator(f"button:has-text('{label}')")
        try:
            btn.first.wait_for(state="visible", timeout=8000)
        except Exception:
            # Screenshot antes de falhar
            report_dir = Path("data/regression_screenshots")
            report_dir.mkdir(parents=True, exist_ok=True)
            ts = os.urandom(4).hex()
            with open(report_dir / f"missing_{page_id}_{ts}.png", "wb") as f:
                f.write(page.screenshot())
            pytest.fail(
                f"Botão '{label}' não encontrado (timeout 8s). "
                f"Screenshot salvo em data/regression_screenshots/missing_{page_id}_{ts}.png"
            )
        btn.first.click()
        app.wait_for_timeout(2500)
        check_for_errors(app, f"tab_{page_id}")

    def test_precos_filter(self, logged_in_app_and_page):
        """Preços: seleciona ingrediente."""
        app, page = logged_in_app_and_page
        app = wake_if_sleeping(page, app)
        app.locator("button:has-text('Precos')").first.wait_for(state="visible", timeout=8000)
        app.locator("button:has-text('Precos')").first.click()
        app.wait_for_timeout(2000)
        check_for_errors(app, "precos")
        selects = app.locator("select, [data-testid='stSelectbox']")
        if selects.count() > 0:
            selects.first.click()
            app.wait_for_timeout(500)
            try:
                selects.first.select_option(index=1)
            except Exception:
                pass
            app.wait_for_timeout(1000)
        check_for_errors(app, "precos_filter")

    def test_revisao_if_pending(self, logged_in_app_and_page):
        """Revisão: se houver itens pendentes."""
        app, page = logged_in_app_and_page
        app = wake_if_sleeping(page, app)
        app.locator("button:has-text('Revisao')").first.wait_for(state="visible", timeout=8000)
        app.locator("button:has-text('Revisao')").first.click()
        app.wait_for_timeout(3000)
        check_for_errors(app, "revisao")
        approve_btn = app.locator("button:has-text('Aprovar')").first
        if approve_btn.count() > 0 and approve_btn.is_visible():
            approve_btn.click()
            app.wait_for_timeout(1000)
            confirm = app.locator("button:has-text('Sim, aprovar')").first
            if confirm.count() > 0:
                confirm.click()
                app.wait_for_timeout(2000)
            check_for_errors(app, "revisao_approve")

    def test_calculadora(self, logged_in_app_and_page):
        """Calculadora carrega sem erro e tabs trocam via selectbox."""
        app, page = logged_in_app_and_page
        app = wake_if_sleeping(page, app)
        app.locator("button:has-text('Calculadora')").first.wait_for(state="visible", timeout=8000)
        app.locator("button:has-text('Calculadora')").first.click()
        app.wait_for_timeout(3000)
        check_for_errors(app, "calculadora")

        # Trocar tabs via selectbox (antes st.tabs, agora st.selectbox)
        select = app.locator("select, [data-testid='stSelectbox'] select").first
        if select.count() > 0:
            # Modo Completo (index 1)
            select.select_option(index=1)
            app.wait_for_timeout(2000)
            check_for_errors(app, "calculadora_tab_completo")

            # Receitas Salvas (index 2)
            select.select_option(index=2)
            app.wait_for_timeout(2000)
            check_for_errors(app, "calculadora_tab_receitas")

            # Voltar para Modo Simples (index 0)
            select.select_option(index=0)
            app.wait_for_timeout(2000)
            check_for_errors(app, "calculadora_tab_simples")

    def test_diagnostico(self, logged_in_app_and_page):
        """Diagnóstico carrega sem erro."""
        app, page = logged_in_app_and_page
        app = wake_if_sleeping(page, app)
        app.locator("button:has-text('Diagnostico')").first.wait_for(state="visible", timeout=8000)
        app.locator("button:has-text('Diagnostico')").first.click()
        app.wait_for_timeout(2000)
        check_for_errors(app, "diagnostico")
        run_all = app.locator("button:has-text('Executar Todos')").first
        if run_all.count() > 0 and run_all.is_visible():
            run_all.click()
            app.wait_for_timeout(5000)
            check_for_errors(app, "diagnostico_run")


class TestFlyerImages:
    """D9 — Health check das URLs de imagem dos flyers"""

    def test_flyer_image_urls_accessible(self):
        """Verifica se URLs de imagem dos flyers são acessíveis (HEAD request)"""
        import httpx
        from dotenv import load_dotenv

        load_dotenv()
        from supabase import create_client
        import os

        c = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
        r = c.table("flyers").select("image_url").neq("image_url", "").limit(30).execute()
        broken = []
        for flyer in r.data or []:
            url = flyer.get("image_url", "")
            if url:
                try:
                    resp = httpx.head(url, timeout=10, follow_redirects=True)
                    if resp.status_code >= 400:
                        broken.append(f"{url[:80]}... HTTP {resp.status_code}")
                except Exception as e:
                    broken.append(f"{url[:80]}... {e}")
        assert len(broken) == 0, f"D9: {len(broken)} imagens quebradas:\n" + "\n".join(broken[:5])
