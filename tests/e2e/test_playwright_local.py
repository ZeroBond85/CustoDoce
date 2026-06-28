"""Automated Streamlit dashboard test with Playwright."""

import sys  # noqa: E402
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

APP_URL = "http://localhost:8501"
SCREENSHOTS_DIR = "C:\\Zerobond\\Code\\CustoDoce\\tests\\screenshots"


def safe_str(s):
    return s.encode("ascii", "replace").decode() if isinstance(s, str) else str(s)


def test_streamlit():
    import os

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on(
            "console", lambda msg: errors.append(f"CONSOLE {msg.type}: {msg.text}") if msg.type == "error" else None
        )

        print("1. Opening app...")
        page.goto(APP_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/01_login.png")
        print(f"   Title: {page.title()}")
        print(f"   Errors so far: {len(errors)}")

        # Try to login
        print("2. Attempting login...")
        try:
            user_input = page.locator(
                'input[aria-label*="user"], input[aria-label*="usuario"], input[aria-label*="Usuario"], input[aria-label*="User"], input[data-testid="stTextInput"]'
            ).first
            if user_input.is_visible(timeout=5000):
                user_input.fill("admin")
                pass_input = page.locator('input[type="password"]').first
                if pass_input.is_visible(timeout=3000):
                    pass_input.fill("custodoce2907")
                    login_btn = page.locator(
                        'button:has-text("Entrar"), button:has-text("Login"), button:has-text("Entrar"), button[data-testid="stFormSubmitButton"]'
                    ).first
                    if login_btn.is_visible(timeout=3000):
                        login_btn.click()
                        page.wait_for_timeout(5000)
                        print("   Login submitted")
                    else:
                        print("   Login button not found")
                else:
                    print("   Password input not found")
            else:
                print("   User input not found, checking if already logged in...")
        except Exception as e:
            print(f"   Login error: {e}")

        page.screenshot(path=f"{SCREENSHOTS_DIR}/02_after_login.png")

        # Get sidebar nav items
        print("3. Checking sidebar navigation...")
        sidebar = page.locator('[data-testid="stSidebar"]')
        nav_items = sidebar.locator('a, button, [role="tab"]').all()
        print(f"   Found {len(nav_items)} sidebar items")

        # Collect all sidebar text
        sidebar_text = sidebar.inner_text()
        print(f"   Sidebar text (first 500 chars): {sidebar_text[:500].encode('ascii', 'replace').decode()}")

        # Investigate sidebar DOM structure
        sidebar_html = sidebar.evaluate("el => el.innerHTML")
        with open(f"{SCREENSHOTS_DIR}/sidebar_dom.txt", "w", encoding="utf-8") as f:
            f.write(sidebar_html[:5000])
        print(f"   Sidebar DOM saved ({len(sidebar_html)} chars)")

        # Try all clickable things
        all_elements = sidebar.locator("*").all()
        clickable = []
        for el in all_elements:
            try:
                tag = el.evaluate("el => el.tagName")
                if tag in ["A", "BUTTON"] or el.evaluate("el => el.getAttribute('role')") in ["button", "tab"]:
                    txt = safe_str(el.inner_text())[:50]
                    if txt and len(txt) > 1:
                        clickable.append({"tag": tag, "text": txt, "el": el})
            except Exception:  # nosec  # noqa: S110
                pass
        print(f"   Found {len(clickable)} clickable elements in sidebar")
        for c in clickable[:20]:
            print(f"     <{c['tag']}> '{c['text']}'")

        for i, c in enumerate(clickable):
            try:
                text = c["text"]
                print(f"\n4.{i + 1}. Clicking '{text}'...")
                c["el"].click()
                page.wait_for_timeout(5000)
                page.screenshot(path=f"{SCREENSHOTS_DIR}/03_page_{i + 1}.png")

                # Check for errors in the main content
                main_content = page.locator('[data-testid="stAppViewBlockContainer"]')
                content_text = main_content.inner_text() if main_content.is_visible(timeout=3000) else ""
                has_error = (
                    "error" in content_text.lower()
                    or "erro" in content_text.lower()
                    or "traceback" in content_text.lower()
                )
                has_data = len(content_text) > 100

                status = "ERROR" if has_error else ("OK (data)" if has_data else "OK (empty)")
                print(f"   Status: {status} | Content length: {len(content_text)} chars")
                results.append({"page": text, "status": status, "content_len": len(content_text)})

                if has_error:
                    print(f"   Error content: {safe_str(content_text[:300])}")

            except Exception as e:
                print(f"   Error on page: {e}")
                results.append({"page": f"page_{i}", "status": f"EXCEPTION: {e}", "content_len": 0})

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for r in results:
            print(f"  {r['page']:40s} | {r['status']:30s} | {r['content_len']:6d} chars")
        print(f"\nTotal console errors: {len(errors)}")
        if errors:
            for e in errors[:10]:
                print(f"  - {e[:200]}")

        browser.close()


if __name__ == "__main__":
    test_streamlit()
