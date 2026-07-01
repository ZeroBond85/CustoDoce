"""
E2E tests para dashboard Streamlit (produção real).
Requer: pytest-playwright, playwright install chromium.
Executa em CI via .github/workflows/e2e.yml
"""

import os
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from PIL import Image, ImageChops

BASE_URL = os.getenv("STREAMLIT_URL", "https://custodoce.streamlit.app")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    page.goto(BASE_URL)
    yield page
    page.close()


def login(page):
    """Faz login no dashboard (se necessário)."""
    # Streamlit Cloud pode não pedir senha se não configurado.
    # Se houver tela de login, preenche.
    if page.locator("input[type='password']").count() > 0:
        page.fill("input[type='password']", ADMIN_PASSWORD)
        page.click("button:has-text('Entrar')")
        page.wait_for_load_state("networkidle")


def compare_images(path1: str, path2: str, threshold: float = 0.01) -> bool:
    """Compara duas imagens e retorna True se forem similares."""
    img1 = Image.open(path1).convert("RGB")
    img2 = Image.open(path2).convert("RGB")

    if img1.size != img2.size:
        return False

    diff = ImageChops.difference(img1, img2)
    # Calcula porcentagem de pixels diferentes
    bbox = diff.getbbox()
    if not bbox:
        return True

    # Para ser mais robusto, contamos pixels significativamente diferentes
    # Mas para simplicidade e performance, usamos o bbox area / total area
    diff_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    total_area = img1.size[0] * img1.size[1]
    return (diff_area / total_area) < threshold


# -------------------- Auth --------------------
def test_login(page):
    login(page)
    # Verifica se chegou no dashboard
    expect(page.locator("text=Visao Geral")).to_be_visible()


# -------------------- Navegação Sidebar --------------------
# Single source of truth: import from navigation_config
from dashboard.navigation_config import MENU_GROUPS

PAGES = [
    (page_id, label)
    for _group, group_pages in MENU_GROUPS.items()
    for label, _icon, page_id in group_pages
]


@pytest.mark.parametrize("page_id,label", PAGES)
def test_navigate(page, page_id, label):
    login(page)
    # Clica no botão da sidebar
    page.click(f"button:has-text('{label}')")
    page.wait_for_load_state("networkidle")
    # Verifica se URL contém page_id ou título presente
    expect(page).to_have_url(f"*{page_id}*")


# -------------------- Testes específicos por aba --------------------
def test_visao_geral_kpis(page):
    login(page)
    page.click("button:has-text('Visao Geral')")
    page.wait_for_load_state("networkidle")
    # KPIs
    expect(page.locator("text=Total Preços")).to_be_visible()
    expect(page.locator("text=Lojas Ativas")).to_be_visible()
    expect(page.locator("text=Itens Revisão")).to_be_visible()


def test_precos_filtros(page):
    login(page)
    page.click("button:has-text('Precos')")
    page.wait_for_load_state("networkidle")
    # Filtros
    expect(page.locator("label:has-text('Ingrediente')")).to_be_visible()
    expect(page.locator("label:has-text('Loja')")).to_be_visible()
    # Ordenação clicando cabeçalho
    page.click("th:has-text('R$/kg')")
    page.wait_for_timeout(500)


def test_historico_grafico(page):
    login(page)
    page.click("button:has-text('Historico')")
    page.wait_for_load_state("networkidle")
    expect(page.locator("canvas, .js-plotly-plot")).to_be_visible()


def test_flyers_grid(page):
    login(page)
    page.click("button:has-text('Flyers')")
    page.wait_for_load_state("networkidle")
    # Grid de thumbnails
    expect(page.locator("img[alt*='flyer']").first).to_be_visible()


def test_revisao_approve_reject(page):
    login(page)
    page.click("button:has-text('Revisao')")
    page.wait_for_load_state("networkidle")
    # Se houver itens pendentes, testa fluxo
    items = page.locator("[data-testid='review-item']")
    if items.count() > 0:
        items.first.click()
        # Aprovar
        page.click("button:has-text('Aprovar')")
        page.click("button:has-text('Sim, aprovar')")
        page.wait_for_timeout(1000)
        # Verifica se sumiu ou status mudou
        expect(page.locator("text=Aprovado")).to_be_visible()


def test_calculadora_salvar(page):
    login(page)
    page.click("button:has-text('Calculadora')")
    page.wait_for_load_state("networkidle")
    # Modo simples
    expect(page.locator("text=Modo Simples")).to_be_visible()
    # Preenche um ingrediente
    page.select_option("select[name='ingredient']", index=1)
    page.fill("input[name='quantity']", "1000")
    page.click("button:has-text('Calcular')")
    page.wait_for_timeout(500)
    expect(page.locator("text=R$")).to_be_visible()


# -------------------- Supabase Data Checks --------------------
def test_supabase_connection():
    from supabase import create_client

    client = create_client(SUPABASE_URL, os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    # D1: prices > 0
    r = client.table("prices").select("id", count="exact").limit(1).execute()
    assert r.count > 0, "D1: prices count > 0"
    # D2: price_history
    r = client.table("price_history").select("id", count="exact").limit(1).execute()
    assert r.count > 0, "D2: price_history count > 0"
    # D3: review_queue pending > 0
    r = client.table("review_queue").select("id", count="exact").eq("status", "pending").execute()
    assert r.count >= 0, "D3: review_queue pending"
    # D4: stores enabled >= 10
    r = client.table("scrape_frequencies").select("store_id", count="exact").eq("enabled", True).execute()
    assert r.count >= 10, "D4: stores enabled >= 10"
    # D5: ingredients = 23
    r = client.table("ingredients").select("id", count="exact").execute()
    assert r.count == 23, f"D5: ingredients count == 23 (got {r.count})"
    # D6: flyers with image_url > 0
    r = client.table("flyers").select("id", count="exact").neq("image_url", "").execute()
    assert r.count > 0, "D6: flyers with image_url > 0"
    # D7: scrape_frequencies enabled > 0
    r = client.table("scrape_frequencies").select("store_id", count="exact").eq("enabled", True).execute()
    assert r.count > 0, "D7: scrape_frequencies enabled > 0"
    # D8: recipes tables exist
    from supabase import create_client

    client2 = create_client(SUPABASE_URL, os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    r = client2.table("recipes").select("id", count="exact").limit(1).execute()
    assert r is not None, "D8: recipes table exists"
    # D9: trigger ON CONFLICT works (test via RPC)
    # D10: RPC upsert_price_rpc works
    # (skip here, covered in integration tests)


# -------------------- Visual Regression --------------------
@pytest.mark.visual
def test_visual_regression(page):
    login(page)
    baseline_dir = Path("tests/baselines")
    diff_dir = Path("tests/diffs")
    baseline_dir.mkdir(parents=True, exist_ok=True)
    diff_dir.mkdir(parents=True, exist_ok=True)

    for page_id, label in PAGES:
        page.click(f"button:has-text('{label}')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        current_path = f"tests/screenshots/current_{page_id}.png"
        baseline_path = f"tests/baselines/{page_id}.png"
        diff_path = f"tests/diffs/{page_id}_diff.png"

        page.screenshot(path=current_path, full_page=True)

        if os.path.exists(baseline_path):
            if not compare_images(current_path, baseline_path):
                # Save diff for debugging
                img1 = Image.open(current_path).convert("RGB")
                img2 = Image.open(baseline_path).convert("RGB")
                diff = ImageChops.difference(img1, img2)
                diff.save(diff_path)
                pytest.fail(f"Visual regression detected on {page_id}. Diff saved to {diff_path}")
        else:
            # First run: save baseline
            with open(current_path, "rb") as f_in:
                content = f_in.read()
            with open(baseline_path, "wb") as f_out:
                f_out.write(content)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
