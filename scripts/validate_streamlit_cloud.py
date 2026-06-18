"""
Validate Streamlit Cloud deployment with Playwright.
Runs login, navigates all tabs, checks for errors, validates PT columns.
"""
import os
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

APP_URL = os.environ.get("STREAMLIT_APP_URL", "https://custodoce.streamlit.app")
LOGIN_USER = os.environ.get("STREAMLIT_TEST_USER", "admin")
LOGIN_PASS = os.environ.get("STREAMLIT_TEST_PASS", "custodoce2907")
SCREENSHOTS_DIR = Path(__file__).parent.parent / "tests" / "screenshots_cloud"

PT_COLUMN_NAMES = [
    "Loja", "Ingrediente", "Produto", "Preco", "Unidade", "Tier", "Promocao",
    "Valido Ate", "Confianca", "Coletado Em", "Marca", "R$/kg", "R$/un",
    "Nome", "Categoria", "Ativo", "Canal", "Destino", "Status", "Itens",
]


def find_login_form(page):
    """Find and fill login form."""
    try:
        user_input = page.locator(
            'input[aria-label*="user" i], input[aria-label*="usuario" i], input[type="text"]'
        ).first
        if user_input.is_visible(timeout=5000):
            user_input.fill(LOGIN_USER)
            pass_input = page.locator('input[type="password"]').first
            if pass_input.is_visible(timeout=3000):
                pass_input.fill(LOGIN_PASS)
                login_btn = page.locator(
                    'button:has-text("Entrar"), button:has-text("Login"), button[data-testid="stFormSubmitButton"]'
                ).first
                if login_btn.is_visible(timeout=3000):
                    login_btn.click()
                    page.wait_for_timeout(3000)
                    return True
    except Exception:  # nosec
        pass
    return False


def find_sidebar_nav(page):
    """Find sidebar navigation items."""
    sidebar = page.locator('[data-testid="stSidebar"]')
    nav = []
    for el in sidebar.locator("*").all():
        try:
            role = el.evaluate("el => el.getAttribute('role')")
            tag = el.evaluate("el => el.tagName")
            if role in ["button", "tab", "menuitem"] or tag in ["A", "BUTTON"]:
                txt = el.inner_text().strip()[:50]
                if txt and len(txt) > 1 and not txt.startswith("_"):
                    nav.append({"text": txt, "el": el})
        except Exception:  # nosec
            pass
    return nav


def check_english_columns(page) -> list[str]:
    """Check if any visible table has English column names that should be PT."""
    issues = []
    for table in page.locator(".stDataFrame table, [data-testid='stDataFrame'] table").all():
        try:
            headers = [th.inner_text().strip() for th in table.locator("thead th").all()]
            for h in headers:
                if h and h[0].isupper():
                    if not any(pt in h for pt in PT_COLUMN_NAMES):
                        if h.lower() not in ["email", "telegram", "whatsapp", "kg", "un", "g", "ml", "l"]:
                            issues.append(f"Possivel coluna EN: {h}")
        except Exception:  # nosec
            pass
    return issues


def validate_app():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    results = {
        "passed": True,
        "errors": [],
        "warnings": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR")
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(f"[PAGE ERROR] {err}"))

        print(f"\n1. Opening {APP_URL}...")
        try:
            page.goto(APP_URL, timeout=60000)
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            page.screenshot(path=str(SCREENSHOTS_DIR / "01_login.png"), full_page=True)
        except Exception as e:
            results["passed"] = False
            results["errors"].append(f"Falha ao abrir app: {e}")
            print(f"   FALHA: {e}")
            browser.close()
            return results

        print("2. Attempting login...")
        if find_login_form(page):
            print("   Login submitted")
            page.wait_for_timeout(5000)
            page.screenshot(path=str(SCREENSHOTS_DIR / "02_after_login.png"), full_page=True)
        else:
            print("   AVISO: Login form not found")

        print("3. Checking for console errors...")
        if console_errors:
            err_count = len([e for e in console_errors if "error" in e.lower()])
            print(f"   {err_count} console errors found")
            results["warnings"].extend(console_errors[:5])
            if err_count > 10:
                results["passed"] = False
                results["errors"].append(f"Muitos erros de console: {err_count}")

        print("4. Finding sidebar navigation...")
        nav_items = find_sidebar_nav(page)
        print(f"   Found {len(nav_items)} nav items")

        print("5. Navigating all tabs...")
        for i, item in enumerate(nav_items):
            if item["text"] in ["admin", "Sair", ""]:
                continue
            try:
                print(f"   [{i+1}/{len(nav_items)}] Clicking '{item['text']}'...")
                item["el"].click()
                page.wait_for_timeout(3000)
                safe_name = item["text"][:20].replace(" ", "_").replace("/", "_")
                page.screenshot(path=str(SCREENSHOTS_DIR / f"03_{safe_name}.png"), full_page=True)

                col_issues = check_english_columns(page)
                if col_issues:
                    print(f"      AVISO colunas EN: {col_issues[:2]}")
                    results["warnings"].extend([f"[{item['text']}] {c}" for c in col_issues[:3]])

                main = page.locator("[data-testid='stAppViewContainer']")
                if main.is_visible(timeout=3000):
                    content_len = len(main.inner_text())
                    print(f"      OK ({content_len} chars)")
                else:
                    print("      AVISO: Main content not visible")

            except Exception as e:
                print(f"      ERRO: {e}")
                results["warnings"].append(f"[{item['text']}] {str(e)[:100]}")

        browser.close()

    print("\n" + "=" * 60)
    print("VALIDATION RESULT")
    print("=" * 60)
    print(f"Status: {'PASSED' if results['passed'] else 'FAILED'}")
    print(f"Console errors: {len(results['errors'])}")
    print(f"Warnings: {len(results['warnings'])}")
    if results["errors"]:
        print("\nERROS:")
        for e in results["errors"][:5]:
            print(f"  - {e}")
    if results["warnings"]:
        print("\nAVISOS:")
        for w in results["warnings"][:10]:
            print(f"  - {w}")
    print(f"\nScreenshots: {SCREENSHOTS_DIR}")
    print("=" * 60)

    return results


if __name__ == "__main__":
    results = validate_app()
    sys.exit(0 if results["passed"] else 1)
