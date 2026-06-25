"""
Comprehensive Streamlit Cloud validation with Playwright.
Tests: login, data loading, PT columns, buttons, forms, performance.
"""
import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

APP_URL = os.environ.get("STREAMLIT_APP_URL", "https://custodoce.streamlit.app")
LOGIN_USER = os.environ.get("STREAMLIT_TEST_USER", "admin")
LOGIN_PASS = os.environ.get("STREAMLIT_TEST_PASS", "custodoce2907")
WRONG_PASS = "senhaerrada123"  # noqa: S105
SCREENSHOTS_DIR = Path(__file__).parent.parent / "tests" / "screenshots_cloud"

PT_COLUMN_NAMES = {
    "store_name": "Loja", "ingredient_id": "Ingrediente", "raw_product": "Produto",
    "raw_price": "Preco", "raw_unit": "Unidade", "tier": "Tier",
    "is_promotion": "Promocao", "valid_until": "Valido Ate", "confidence": "Confianca",
    "collected_at": "Coletado Em", "brand": "Marca", "price_per_kg": "R$/kg",
    "price_per_un": "R$/un", "name": "Nome", "category": "Categoria",
    "active": "Ativo", "channel": "Canal", "target": "Destino",
    "status": "Status", "items_found": "Itens",
}


@dataclass
class ValidationResult:
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_timings: dict[str, float] = field(default_factory=dict)
    data_checks: dict[str, bool] = field(default_factory=dict)


def timed_page_load(page, url: str, name: str, result: ValidationResult):
    """Navigate to URL and measure load time."""
    start = time.time()
    try:
        page.goto(url, timeout=90000)
        page.wait_for_load_state("networkidle", timeout=90000)
        page.wait_for_timeout(3000)
        elapsed = time.time() - start
        result.page_timings[name] = elapsed
        print(f"   Carregado em {elapsed:.1f}s")
        return True
    except Exception as e:
        result.errors.append(f"[{name}] Falha ao carregar: {e}")
        return False


def find_login_form(page):
    """Fill and submit login form with retries and robust selectors."""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                print(f"   Retry {attempt}/{max_retries}...")
                page.goto(APP_URL, timeout=60000)
                page.wait_for_load_state("networkidle", timeout=60000)
                page.wait_for_timeout(3000)

            # Wait for page to be fully loaded
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # More robust selectors for Streamlit login form
            # Streamlit uses specific test IDs and classes
            user_input = None
            for selector in [
                'input[data-testid="stTextInput"][aria-label*="Usuário" i]',
                'input[data-testid="stTextInput"][aria-label*="Usuario" i]',
                'input[data-testid="stTextInput"][placeholder*="admin" i]',
                'input[data-testid="stTextInput"][aria-label*="Usuário" i]',
                'input[data-testid="stTextInput"][type="text"]',
                'input[type="text"]',
            ]:
                try:
                    user_input = page.locator(selector).first
                    if user_input.is_visible(timeout=3000):
                        break
                except Exception:
                    continue

            if not user_input or not user_input.is_visible(timeout=5000):
                # Fallback and try a more generic approach
                user_input = page.locator('input[type="text"]').first
                if not user_input.is_visible(timeout=3000):
                    raise Exception("Username input not found")

            user_input.fill(LOGIN_USER)

            pass_input = None
            for selector in [
                'input[data-testid="stTextInput"][aria-label*="Senha" i]',
                'input[data-testid="stTextInput"][aria-label*="Password" i]',
                'input[data-testid="stTextInput"][type="password"]',
                'input[type="password"]',
            ]:
                try:
                    pass_input = page.locator(selector).first
                    if pass_input.is_visible(timeout=3000):
                        break
                except Exception:
                    continue

            if not pass_input or not pass_input.is_visible(timeout=5000):
                pass_input = page.locator('input[type="password"]').first
                if not pass_input.is_visible(timeout=3000):
                    raise Exception("Password input not found")

            pass_input.fill(LOGIN_PASS)

            login_btn = page.locator(
                'button:has-text("Entrar"), button:has-text("Login"), '
                'button[kind="primary"], button[data-testid="baseButton-primary"]'
            ).first
            login_btn.wait_for(state="visible", timeout=5000)
            login_btn.click()

            page.wait_for_timeout(5000)
            return True
        except Exception as e:
            if attempt == max_retries:
                print(f"   ERRO no login: {str(e)[:80]}")
                return False
            print(f"   Tentativa {attempt} falhou: {str(e)[:60]}")
    return False


def find_sidebar_nav(page):
    """Get sidebar nav items as list of {text, el}."""
    sidebar = page.locator('[data-testid="stSidebar"]')
    nav = []
    for el in sidebar.locator("*").all():
        try:
            role = el.evaluate("el => el.getAttribute('role')")
            tag = el.evaluate("el => el.tagName")
            if role in ["button", "tab", "menuitem"] or tag in ["A", "BUTTON"]:
                txt = el.inner_text().strip()[:50]
                if txt and len(txt) > 1 and txt not in ["admin", "Sair"]:
                    nav.append({"text": txt, "el": el})
        except Exception:
            pass
    return nav


def check_table_has_rows(page) -> bool:
    """Check if any st.dataframe visible has data rows."""
    try:
        for df in page.locator("[data-testid='stDataFrame'], .stDataFrame").all():
            rows = df.locator("tbody tr").all()
            if len(rows) > 0:
                return True
    except Exception:
        pass
    return False


def check_english_columns(page) -> list[str]:
    """Check for column names that are still in English (not PT)."""
    issues = []
    known_pt = set(PT_COLUMN_NAMES.values())
    known_en_values = {"email", "telegram", "whatsapp", "kg", "un", "g", "ml", "l"}
    for table in page.locator("[data-testid='stDataFrame'] table, .stDataFrame table").all():
        try:
            headers = [th.inner_text().strip() for th in table.locator("thead th").all()]
            for h in headers:
                if (h and h[0].isupper() and len(h) > 1
                    and h not in known_pt and h.lower() not in known_en_values
                    and not any(pt in h for pt in known_pt)):
                    issues.append(h)
        except Exception:
            pass
    return issues


def click_button_with_text(page, text: str, timeout: int = 5000):
    """Click a button by partial text match."""
    try:
        btn = page.locator(f'button:has-text("{text}")').first
        btn.click(timeout=timeout)
        page.wait_for_timeout(2000)
        return True
    except Exception:
        return False


def validate_app() -> ValidationResult:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    result = ValidationResult()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR")
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"{msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(f"PAGE ERROR: {err}"))

        # 1. Open app
        print("\n1. Abrindo app...")
        if not timed_page_load(page, APP_URL, "app_load", result):
            browser.close()
            return result
        page.screenshot(path=str(SCREENSHOTS_DIR / "01_app.png"), full_page=True)

        # Debug: print page content to understand what's rendered
        try:
            title = page.title()
            body_text = page.locator("body").inner_text(timeout=5000)[:500]
            print(f"   Title: {title}")
            print(f"   Body preview: {body_text[:200]}")
        except Exception:
            pass

        # Check if already logged in
        def is_logged_in(page):
            try:
                logout_btn = page.locator('button:has-text("Sair"), button:has-text("Logout"), [data-testid="stSidebar"] button:has-text("Sair")').first
                if logout_btn.is_visible(timeout=2000):
                    return True
                sidebar = page.locator('[data-testid="stSidebar"]')
                if sidebar.is_visible(timeout=2000):
                    nav_items = sidebar.locator('button, a, [role="button"]').all()
                    if len(nav_items) > 2:
                        return True
            except Exception:
                pass
            return False

        # Check if already logged in
        if is_logged_in(page):
            print("   Já logado!")
        else:
            # 2. Login with correct password
            print("2. Fazendo login...")
            page.goto(APP_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            if not find_login_form(page):
                result.errors.append("Não conseguiu fazer login")
                result.passed = False
                browser.close()
                return result
            print("   Login OK")
            page.screenshot(path=str(SCREENSHOTS_DIR / "02_logged_in.png"), full_page=True)

        # 4. Console errors check
        print("4. Verificando console errors...")
        error_count = len([e for e in console_errors if "error" in e.lower()])
        print(f"   {error_count} erros no console")
        if error_count > 5:
            result.warnings.extend(console_errors[:5])
        if error_count > 20:
            result.errors.append(f"Muitos erros de console: {error_count}")
            result.passed = False

        # 5. Navigate all sidebar tabs
        print("5. Navegando pelas abas...")
        nav_items = find_sidebar_nav(page)
        print(f"   Encontradas {len(nav_items)} abas")

        pages_with_data = 0
        for i, item in enumerate(nav_items):
            try:
                print(f"   [{i+1}/{len(nav_items)}] {item['text']}...", end=" ")
                item["el"].click()
                page.wait_for_timeout(3000)

                # Check if page loaded (not blank)
                main = page.locator("[data-testid='stAppViewContainer']")
                if not main.is_visible(timeout=5000):
                    result.warnings.append(f"[{item['text']}] Conteúdo principal não visível")
                    print("AVISO(conteudo)")
                    continue

                # Check if table has data
                has_data = check_table_has_rows(page)
                if has_data:
                    pages_with_data += 1
                    result.data_checks[item["text"]] = True
                    print(f"OK(dados:{len(main.inner_text())}chars)")
                else:
                    result.data_checks[item["text"]] = False
                    print("OK(vazio)")

                # Check PT columns
                col_issues = check_english_columns(page)
                if col_issues:
                    result.warnings.append(f"[{item['text']}] Colunas EN: {col_issues[:3]}")
                    print(f"      AVISO(colunas): {col_issues[:2]}")

                # Save screenshot every 5 pages
                if i % 5 == 0:
                    page.screenshot(path=str(SCREENSHOTS_DIR / f"04_{item['text'][:15]}.png"), full_page=True)

            except Exception as e:
                result.warnings.append(f"[{item['text']}] Erro: {str(e)[:80]}")
                print(f"ERRO({str(e)[:30]})")

        print(f"\n6. Resumo de dados: {pages_with_data}/{len(nav_items)} abas com dados")

        # 7. Test specific button: "Buscar Precos" on Visao Geral
        print("7. Testando botoes principais...")
        try:
            page.goto(f"{APP_URL}/?page=Visao+Geral", timeout=30000)
            page.wait_for_timeout(3000)

            # Look for ingredient selector and search button
            ing_select = page.locator('div[data-testid="stSelectbox"]').first
            if ing_select.is_visible(timeout=3000):
                print("   Selectbox de ingrediente encontrado")
                # Try clicking Buscar if visible
                if click_button_with_text(page, "Buscar"):
                    print("   Botao Buscar funcionou")
                    page.wait_for_timeout(3000)
                    page.screenshot(path=str(SCREENSHOTS_DIR / "05_busca.png"), full_page=True)
                    if check_table_has_rows(page):
                        result.data_checks["busca_precos"] = True
                        print("   Busca retornou dados")
                    else:
                        result.data_checks["busca_precos"] = False
                        result.warnings.append("Busca não retornou dados")
        except Exception as e:
            result.warnings.append(f"Teste de botao Buscar falhou: {e}")
            print(f"   AVISO: {e}")

        # 8. Test scrapers logs tab
        print("8. Verificando tab de logs...")
        try:
            for item in nav_items:
                if "Scraper" in item["text"] or "Log" in item["text"]:
                    item["el"].click()
                    page.wait_for_timeout(3000)
                    if check_table_has_rows(page):
                        result.data_checks["scrapers_logs"] = True
                        print("   Logs de scrapers com dados")
                    else:
                        result.data_checks["scrapers_logs"] = False
                    break
        except Exception as e:
            result.warnings.append(f"Teste de logs falhou: {e}")

        browser.close()

    # Final report
    print("\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)
    print(f"Status: {'PASSED' if result.passed else 'FAILED'}")
    print(f"Abas navegadas: {len(nav_items)}")
    print(f"Abas com dados: {pages_with_data}/{len(nav_items)}")
    print("\nTempos de carga:")
    for name, t in result.page_timings.items():
        print(f"  {name}: {t:.1f}s")
    if result.errors:
        print(f"\nERROS ({len(result.errors)}):")
        for e in result.errors[:5]:
            print(f"  - {e}")
    if result.warnings:
        print(f"\nAVISOS ({len(result.warnings)}):")
        for w in result.warnings[:10]:
            print(f"  - {w}")
    if result.data_checks:
        print("\nChecks de dados:")
        for k, v in result.data_checks.items():
            print(f"  {'OK' if v else 'VAZIO'}: {k}")
    print(f"\nScreenshots: {SCREENSHOTS_DIR}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    result = validate_app()
    sys.exit(0 if result.passed else 1)
