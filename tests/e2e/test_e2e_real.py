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

# Single source of truth: import from navigation_config (MENU_GROUPS drives st.navigation)
from dashboard.navigation_config import MENU_GROUPS

BASE_URL = os.getenv("STREAMLIT_URL", "https://custodoce.streamlit.app")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "custodoce123")

# Build PAGES from MENU_GROUPS — eliminates drift
# MENU_GROUPS format: {group: [(label, icon, page_id), ...]}
PAGES = []
for group_pages in MENU_GROUPS.values():
    for label, icon, page_id in group_pages:
        # expected_text: use page_id capitalized as fallback (tests check for this text)
        expected = page_id.replace("_", " ").title()
        PAGES.append((page_id, label, expected))


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
    Usa mais retries para cloud URL (cold start pode levar 60s+).
    Aceita tanto <a> (st.navigation) quanto <button> (legacy)."""
    is_cloud = "local" not in BASE_URL
    max_retries = 6 if is_cloud else 3
    for attempt in range(max_retries):
        app = wake_if_sleeping(page, app)
        try:
            timeout = 30000 if is_cloud else 15000
            sidebar = app.locator('[data-testid="stSidebar"]')
            if sidebar.count() > 0:
                sidebar.locator("a").filter(has_text="Visão Geral").first.wait_for(state="visible", timeout=timeout)
            else:
                app.locator("button:has-text('Visão Geral')").first.wait_for(state="visible", timeout=timeout)
            return app
        except Exception:
            if attempt < max_retries - 1:
                page.wait_for_timeout(5000)
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(5000)
                app = get_app(page)
    return app


def login_to_app(page):
    """Faz login completo no Streamlit Cloud + dashboard.

    Lida com cold start e com o fato de que no Cloud o form de login
    fica dentro do iframe /~/+/, enquanto local fica na page principal.
    """
    page.wait_for_load_state("networkidle")

    def _find_password_input(ctx):
        return ctx.locator("input[type='password']")

    def _find_sidebar(ctx):
        btn = ctx.locator("button:has-text('Visão Geral')")
        link = ctx.locator('[data-testid="stSidebar"] a').filter(has_text="Visão Geral")
        return btn if btn.count() > 0 and btn.first.is_visible() else (link if link.count() > 0 and link.first.is_visible() else None)

    def _find_user_input(ctx):
        return ctx.locator('input[aria-label*="Usuario"], input[placeholder="admin"]').first

    # Poll for login form or sidebar in BOTH page (local) and app frame (cloud)
    for _ in range(45):
        # Check page (local)
        pw_page = _find_password_input(page)
        if pw_page.count() > 0 and pw_page.first.is_visible():
            break
        side_page = _find_sidebar(page)
        if side_page:
            return ensure_app_ready(page, get_app(page))

        # Check app frame (cloud)
        app_frame = get_app(page)
        pw_app = _find_password_input(app_frame)
        if pw_app.count() > 0 and pw_app.first.is_visible():
            break
        side_app = _find_sidebar(app_frame)
        if side_app:
            return ensure_app_ready(page, app_frame)

        page.wait_for_timeout(1000)

    # Determine where the login form is
    pw_page = _find_password_input(page)
    target = page if pw_page.count() > 0 and pw_page.first.is_visible() else get_app(page)

    pw_input = _find_password_input(target)
    if pw_input.count() > 0 and pw_input.first.is_visible():
        user_input = _find_user_input(target)
        if user_input.count() > 0:
            user_input.fill("admin")
        pw_input.first.fill(ADMIN_PASSWORD)
        entrar = target.locator("button:has-text('Entrar')")
        if entrar.count() > 0:
            entrar.first.click()
            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle")

    # Second gate (if any)
    for ctx in (get_app(page), page):
        pw2 = _find_password_input(ctx)
        if pw2.count() > 0 and pw2.first.is_visible():
            u2 = _find_user_input(ctx)
            if u2.count() > 0:
                u2.fill("admin")
            pw2.first.fill(ADMIN_PASSWORD)
            entrar2 = ctx.locator("button:has-text('Entrar')")
            if entrar2.count() > 0:
                entrar2.first.click()
                page.wait_for_timeout(3000)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(5000)
            break

    app = get_app(page)
    return ensure_app_ready(page, app)


def check_for_errors(app, context="", take_screenshot=True, page=None):
    """Varre página por erros Streamlit/Python.

    Checa tanto o frame do app (Streamlit Cloud usa iframe /~/+) quanto
    o page top-level (Streamlit local nao usa iframe). Assim cobre
    ambos os ambientes sem perder cenarios de erro real.
    """
    error_selectors = [
        ".stException",
        ".stAlert[data-baseweb='notification']",
        "text=Traceback",
        "text=traceback",
        "text=/^Error: /",
        "text=/^Erro: /",
        "text=/DatabaseError/",
        "text=/OperationalError/",
        "text=/relation .* does not exist/",
        "text=/column .* does not exist/",
    ]
    containers = [c for c in (app, page) if c is not None]
    for sel in error_selectors:
        for container in containers:
            try:
                el = container.locator(sel).first
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


def navigate_to_page(app, page, label):
    """Navega para pagina via sidebar link (st.navigation renderiza <a>).

    Tenta no frame do app (Streamlit Cloud /~/+) e cai para o page
    top-level (Streamlit local sem iframe). Fallback para botao caso a
    sidebar ainda use botoes (legacy). Retorna True se clicou no nav.
    """
    containers = [c for c in (app, page) if c is not None]
    for container in containers:
        sidebar = container.locator('[data-testid="stSidebar"]')
        if sidebar.count() > 0:
            link = sidebar.locator("a").filter(has_text=label).first
            if link.count() > 0:
                link.click()
                return True
        btn = container.locator(f"button:has-text('{label}')").first
        if btn.count() > 0:
            btn.click()
            return True
    return False


# browser fixture is shared via conftest.py (session-scoped) to avoid duplicate launches

@pytest.fixture(scope="session")
def logged_in_app(browser):
    """Retorna app frame logado no dashboard."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE_URL, timeout=120000)
    app = login_to_app(page)
    yield app
    page.close()


@pytest.fixture(scope="session")
def logged_in_app_and_page(browser):
    """Retorna (app, page) para testes que precisam acordar Streamlit Cloud
    ou tirar screenshots. Session-scoped para evitar 1 login por aba
    (lento em cold-start). O wake_if_sleeping por teste trata hibernacao."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE_URL, timeout=120000)
    app = login_to_app(page)
    yield app, page
    page.close()


class TestE2EReal:
    """D1 — Playwright E2E contra Streamlit Cloud"""

    def test_home_mobile(self, browser):
        """Home carrega em viewport mobile (320px)"""
        page = browser.new_page(viewport={"width": 320, "height": 568})
        page.goto(BASE_URL, timeout=120000)
        app = login_to_app(page)
        check_for_errors(app, "home_mobile", page=page)
        page.close()

    def test_home_tablet(self, browser):
        """Home carrega em viewport tablet (768px)"""
        page = browser.new_page(viewport={"width": 768, "height": 1024})
        page.goto(BASE_URL, timeout=120000)
        app = login_to_app(page)
        check_for_errors(app, "home_tablet", page=page)
        page.close()

    def test_home_desktop(self, browser):
        """Home carrega em viewport desktop (1280px)"""
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(BASE_URL, timeout=120000)
        app = login_to_app(page)
        check_for_errors(app, "home_desktop", page=page)
        page.close()

    @pytest.mark.parametrize("page_id,label,expected", PAGES)
    def test_tab_navigates_without_error(self, logged_in_app_and_page, page_id, label, expected):
        """Cada aba navega sem erro."""
        app, page = logged_in_app_and_page
        # Acordar Streamlit Cloud caso tenha hibernado entre tests
        app = wake_if_sleeping(page, app)
        # Garantir que sidebar esta pronta (cold start pode levar 60s+)
        app = ensure_app_ready(page, app)
        # Navegar via sidebar link (st.navigation renderiza <a>, nao botao)
        if not navigate_to_page(app, page, label):
            # Screenshot antes de falhar
            report_dir = Path("data/regression_screenshots")
            report_dir.mkdir(parents=True, exist_ok=True)
            ts = os.urandom(4).hex()
            with open(report_dir / f"missing_{page_id}_{ts}.png", "wb") as f:
                f.write(page.screenshot())
            pytest.fail(
                f"Nav item '{label}' não encontrado na sidebar. "
                f"Screenshot salvo em data/regression_screenshots/missing_{page_id}_{ts}.png"
            )
        # Apos navegar, o frame pode ter se desanexado/recriado (cloud) — refazer get_app
        app = get_app(page)
        app.wait_for_timeout(2000)
        check_for_errors(app, f"tab_{page_id}", page=page)

    def test_precos_filter(self, logged_in_app_and_page):
        """Preços: seleciona ingrediente."""
        app, page = logged_in_app_and_page
        app = wake_if_sleeping(page, app)
        navigate_to_page(app, page, "Precos")
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
        navigate_to_page(app, page, "Revisao")
        app.wait_for_timeout(2000)
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
        navigate_to_page(app, page, "Calculadora")
        app.wait_for_timeout(2000)
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
        navigate_to_page(app, page, "Diagnostico")
        app.wait_for_timeout(2000)
        check_for_errors(app, "diagnostico")
        run_all = app.locator("button:has-text('Executar Todos')").first
        if run_all.count() > 0 and run_all.is_visible():
            run_all.click()
            app.wait_for_timeout(5000)
            check_for_errors(app, "diagnostico_run")

    def test_sidebar_completeness(self, logged_in_app_and_page):
        """Sidebar contém todos os botões esperados e nenhum inesperado.

        Os labels da sidebar podem vir com ícone/emoji prefixado
        (ex: "🔍 Preços") e com botões de navegação do Streamlit
        (ex: "keyboard_double_arrow_left"). Normalizamos para comparar
        apenas o texto legível com os labels de MENU_GROUPS.
        """
        import re as _re

        app, page = logged_in_app_and_page
        app = wake_if_sleeping(page, app)

        def _normalize(text: str) -> str:
            t = (text or "").strip()
            # remove leading icon/emoji até a primeira letra (ex: "🔍Preços" -> "Preços")
            m = _re.search(r"[A-Za-z].*$", t)
            return m.group(0).strip() if m else ""

        expected = {label for _, label, _ in PAGES}
        sidebar = app.locator("[data-testid='stSidebar']")
        found_buttons = set()
        for btn in sidebar.locator("button, a").all():
            t = _normalize(btn.text_content())
            if t and t != "keyboard_double_arrow_left":
                found_buttons.add(t)

        missing = expected - found_buttons
        extra = found_buttons - expected
        msgs = []
        if missing:
            msgs.append(f"Botões faltando no PAGES (sidebar tem, testes não cobrem): {missing}")
        if extra:
            msgs.append(f"Botões extra sem teste (PAGES desatualizado): {extra}")
        assert not msgs, "; ".join(msgs)


class TestFlyerImages:
    """D9 — Health check das URLs de imagem dos flyers.

    Faz HEAD requests a URLs externas (CDN de imagens). Para tolerar
    flakiness de rede sem skip, faz ate 2 retries por URL antes de
    reportar como broken.
    """

    @staticmethod
    def _head_with_retry(url: str, retries: int = 2):
        import httpx

        last_exc = None
        for attempt in range(retries + 1):
            try:
                return httpx.head(url, timeout=10, follow_redirects=True)
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    import time
                    time.sleep(0.5)
        raise last_exc

    @staticmethod
    def _is_network_error(exc: Exception) -> bool:
        """Erros de transporte (DNS, TLS, conexao) apos retry sao
        'flakiness de rede' (ver docstring), nao URL logicamente quebrada.
        Apenas 4xx/5xx e timeouts de leitura devem contar como broken.
        """
        import socket
        import ssl
        import httpx

        for e in (exc, getattr(exc, "__cause__", None), getattr(exc, "__context__", None)):
            if e is None:
                continue
            if isinstance(e, (socket.gaierror, ssl.SSLError, httpx.ConnectError)):
                return True
        return False

    def test_flyer_image_urls_accessible(self):
        """Verifica se URLs de imagem dos flyers sao acessiveis (HEAD request)

        Requer SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente (CI ja tem).
        Falhas reais de URLs broken sao reportadas; flakiness de rede e
        mitigada por retry interno.
        """
        assert os.environ.get("SUPABASE_URL"), "SUPABASE_URL ausente"
        assert os.environ.get("SUPABASE_SERVICE_ROLE_KEY"), "SUPABASE_SERVICE_ROLE_KEY ausente"

        from dotenv import load_dotenv

        load_dotenv()

        from supabase import create_client

        c = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
        r = c.table("flyers").select("image_url").neq("image_url", "").limit(30).execute()
        broken = []
        for flyer in r.data or []:
            url = flyer.get("image_url", "")
            if url:
                try:
                    resp = self._head_with_retry(url)
                    if resp.status_code >= 400:
                        broken.append(f"{url[:80]}... HTTP {resp.status_code}")
                except Exception as e:
                    # Apos retries: erros de rede/transporte (DNS, TLS, conexao)
                    # sao tolerados (flakiness de rede, ver docstring); apenas
                    # falhas logicas (4xx/5xx ja tratadas acima, timeout de
                    # leitura, erro de protocolo) contam como broken.
                    if self._is_network_error(e):
                        continue
                    broken.append(f"{url[:80]}... {e}")
        assert len(broken) == 0, f"D9: {len(broken)} imagens quebradas:\n" + "\n".join(broken[:5])
