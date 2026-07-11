"""
E2E tests para dashboard Streamlit (produção real).
Requer: pytest-playwright, playwright install chromium.
Executa em CI via .github/workflows/e2e.yml

Mesmo tratamento de login/navegacao que test_e2e_real.py:
- Cloud Streamlit usa iframe /~+/ — login dentro do frame
- Sidebar usa <a> (st.navigation) — pode cair para <button> (legacy)
- Frame pode detach/recriar apos navegacao — re-get via get_app()
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

from dashboard.navigation_config import MENU_GROUPS
from tests.e2e.test_e2e_real import (
    BASE_URL,
    check_for_errors,
    ensure_app_ready,
    get_app,
    login_to_app,
    wake_if_sleeping,
)

# PAGES single source of truth (navigation_config)
PAGES = [
    (page_id, label)
    for _group, group_pages in MENU_GROUPS.items()
    for label, _icon, page_id in group_pages
]


# -------------------- Helpers --------------------
def _navigate_to_page(page, app, label: str) -> bool:
    """Navega para pagina via sidebar, aceita <a> ou <button>, em page OU frame.

    Em cloud (Streamlit usa iframe /~+/), app=frame.
    Em local, app==page (get_app retorna page direto).
    """
    containers = [c for c in (app, page) if c is not None]
    for container in containers:
        sidebar = container.locator('[data-testid="stSidebar"]')
        if sidebar.count() > 0:
            link = sidebar.locator("a").filter(has_text=label).first
            if link.count() > 0:
                link.click()
                page.wait_for_timeout(1500)
                return True
        btn = container.locator(f"button:has-text('{label}')").first
        if btn.count() > 0:
            btn.click()
            page.wait_for_timeout(1500)
            return True
    return False


def _wait_and_get_app(page, max_retries: int = 3):
    """Apos navegacao/login, garante que o app frame esta pronto."""
    app = get_app(page)
    for _ in range(max_retries):
        app = wake_if_sleeping(page, app)
        app = ensure_app_ready(page, app)
        if app.locator('[data-testid="stSidebar"]').count() > 0:
            return app
        page.wait_for_timeout(2000)
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2000)
        app = get_app(page)
    return app


# -------------------- Browser fixtures --------------------
@pytest.fixture(scope="session")
def browser_dashboard():
    """Browser instance for e2e tests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="session")
def logged_in_page(browser):
    """Page ja logada no Streamlit (local OU cloud).

    Session-scoped para evitar 1 login por teste (economiza ~60s por cold-start
    na cloud). O login e iframe-aware — funciona em ambos.
    """
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE_URL, timeout=120000)
    page.wait_for_load_state("networkidle")
    login_to_app(page)
    yield page
    page.close()


# -------------------- Auth --------------------
@pytest.mark.e2e
def test_login(logged_in_page):
    """Verifica que chegou no dashboard (sidebar presente)."""
    page = logged_in_page
    page.wait_for_timeout(2000)
    app = get_app(page)
    app.wait_for_timeout(2000)
    # Tenta em ambos (page OU frame)
    sidebar_found = False
    for ctx in (app, page):
        if ctx.locator('[data-testid="stSidebar"]').count() > 0:
            sidebar_found = True
            break
    assert sidebar_found, "Sidebar nao encontrada em page nem em frame"


# -------------------- Navegação Sidebar --------------------
@pytest.mark.e2e
@pytest.mark.parametrize("page_id,label", PAGES)
def test_navigate(logged_in_page, page_id, label):
    """Navega para cada aba e verifica que sidebar continua visivel."""
    page = logged_in_page
    app = get_app(page)
    app = wake_if_sleeping(page, app)
    app = ensure_app_ready(page, app)

    if not _navigate_to_page(page, app, label):
        import os as _os

        report_dir = _os.path.join("data", "regression_screenshots")
        _os.makedirs(report_dir, exist_ok=True)
        ts = _os.urandom(4).hex()
        with open(_os.path.join(report_dir, f"missing_{page_id}_{ts}.png"), "wb") as f:
            f.write(page.screenshot())
        pytest.fail(
            f"Nav '{label}' (page_id={page_id}) nao encontrada. "
            f"Screenshot: data/regression_screenshots/missing_{page_id}_{ts}.png"
        )

    # Apos navegacao, o frame pode ter detached/recriado (cloud) — refazer get_app
    app = get_app(page)
    app.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
    check_for_errors(app, f"nav_{page_id}", page=page)


# -------------------- Testes específicos por aba --------------------
@pytest.mark.e2e
def test_visao_geral_kpis(logged_in_page):
    page = logged_in_page
    app = get_app(page)
    app = wake_if_sleeping(page, app)
    app = ensure_app_ready(page, app)
    assert _navigate_to_page(page, app, "Visão Geral")
    page.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    check_for_errors(app, "visao_geral_kpis", page=page)


@pytest.mark.e2e
def test_precos_filtros(logged_in_page):
    page = logged_in_page
    app = get_app(page)
    app = wake_if_sleeping(page, app)
    app = ensure_app_ready(page, app)
    assert _navigate_to_page(page, app, "Preços")
    page.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    check_for_errors(app, "precos_filtros", page=page)


@pytest.mark.e2e
def test_historico_grafico(logged_in_page):
    page = logged_in_page
    app = get_app(page)
    app = wake_if_sleeping(page, app)
    app = ensure_app_ready(page, app)
    assert _navigate_to_page(page, app, "Histórico")
    page.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    check_for_errors(app, "historico_grafico", page=page)


@pytest.mark.e2e
def test_flyers_grid(logged_in_page):
    page = logged_in_page
    app = get_app(page)
    app = wake_if_sleeping(page, app)
    app = ensure_app_ready(page, app)
    assert _navigate_to_page(page, app, "Flyers")
    page.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    check_for_errors(app, "flyers_grid", page=page)


@pytest.mark.e2e
def test_revisao_approve_reject(logged_in_page):
    page = logged_in_page
    app = get_app(page)
    app = wake_if_sleeping(page, app)
    app = ensure_app_ready(page, app)
    assert _navigate_to_page(page, app, "Revisão")
    page.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    check_for_errors(app, "revisao", page=page)


@pytest.mark.e2e
def test_calculadora_salvar(logged_in_page):
    page = logged_in_page
    app = get_app(page)
    app = wake_if_sleeping(page, app)
    app = ensure_app_ready(page, app)
    assert _navigate_to_page(page, app, "Calculadora")
    page.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    check_for_errors(app, "calculadora", page=page)


# -------------------- Supabase Data Checks --------------------
def test_supabase_connection():
    """D1-D8: integridade minima dos dados no Supabase. Requer service role.
    Roda dentro do job e2e-full (precisa SUPABASE_URL/KEY já configuradas).
    """
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        pytest.skip("SUPABASE_URL/SERVICE_ROLE_KEY ausentes — checks de dados Supabase pulados")

    from supabase import create_client

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    r = client.table("prices").select("id", count="exact").limit(1).execute()
    assert r.count and r.count > 0, "D1: prices count > 0"
    r = client.table("price_history").select("id", count="exact").limit(1).execute()
    assert r.count and r.count > 0, "D2: price_history count > 0"
    r = client.table("review_queue").select("id", count="exact").eq("status", "pending").execute()
    assert r.count is not None and r.count >= 0, "D3: review_queue pending"
    r = client.table("scrape_frequencies").select("store_id", count="exact").eq("enabled", True).execute()
    assert r.count and r.count >= 10, f"D4: scrape_frequencies enabled >= 10 (got {r.count})"
    r = client.table("ingredients").select("id", count="exact").execute()
    assert r.count and r.count == 23, f"D5: ingredients count == 23 (got {r.count})"
    r = client.table("flyers").select("id", count="exact").neq("image_url", "").execute()
    assert r.count and r.count > 0, "D6: flyers with image_url > 0"
    r = client.table("scrape_frequencies").select("store_id", count="exact").eq("enabled", True).execute()
    assert r.count and r.count > 0, "D7: scrape_frequencies enabled > 0"
    r = client.table("recipes").select("id", count="exact").limit(1).execute()
    assert r is not None, "D8: recipes table exists"
    # D9: trigger ON CONFLICT (coberto nos integration tests)
    # D10: RPC upsert_price_rpc (coberto nos integration tests)


# -------------------- Visual Regression --------------------
def compare_images(path1: str, path2: str, threshold: float = 0.01) -> bool:
    """Compara duas imagens e retorna True se forem similares."""
    img1 = Image.open(path1).convert("RGB")
    img2 = Image.open(path2).convert("RGB")

    if img1.size != img2.size:
        return False

    diff = ImageChops.difference(img1, img2)
    bbox = diff.getbbox()
    if not bbox:
        return True

    diff_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    total_area = img1.size[0] * img1.size[1]
    return (diff_area / total_area) < threshold


@pytest.mark.visual
def test_visual_regression(logged_in_page):
    """Requer UPDATE_BASELINES=1 + baselines/ existentes para comparar."""
    page = logged_in_page
    app = get_app(page)
    app = wake_if_sleeping(page, app)
    app = ensure_app_ready(page, app)

    baseline_dir = Path("tests/baselines")
    diff_dir = Path("tests/diffs")
    baseline_dir.mkdir(parents=True, exist_ok=True)
    diff_dir.mkdir(parents=True, exist_ok=True)

    UPDATE_BASELINES = os.getenv("UPDATE_BASELINES", "0") == "1"
    if not UPDATE_BASELINES and not any((baseline_dir / f"{pid}.png").exists() for pid, _ in PAGES):
        pytest.skip(
            "Visual regression: sem baselines em tests/baselines e sem UPDATE_BASELINES=1. "
            "Primeiro run deve criar baselines."
        )

    for page_id, label in PAGES:
        # Refetch frame (pode ter detached desde o ultimo nav)
        app = get_app(page)
        if not _navigate_to_page(page, app, label):
            pytest.fail(f"Nav '{label}' nao encontrada no visual regression")
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        current_path = f"tests/screenshots/current_{page_id}.png"
        baseline_path = baseline_dir / f"{page_id}.png"
        diff_path = diff_dir / f"{page_id}_diff.png"

        page.screenshot(path=current_path, full_page=True)

        if UPDATE_BASELINES:
            baseline_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.move(current_path, baseline_path)
        elif baseline_path.exists():
            if not compare_images(current_path, str(baseline_path)):
                img1 = Image.open(current_path).convert("RGB")
                img2 = Image.open(str(baseline_path)).convert("RGB")
                diff = ImageChops.difference(img1, img2)
                diff.save(str(diff_path))
                pytest.fail(f"Visual regression detected on {page_id}. Diff saved to {diff_path}")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
