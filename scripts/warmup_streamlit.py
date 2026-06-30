"""Warm up Streamlit Cloud app via Playwright (headless Chromium).

Streamlit Cloud is now an SPA (React) — HTTP requests only get the shell
HTML (<div id='root'></div>). Real warmup needs a browser that runs JS.
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

_NETWORK_IDLE_TIMEOUT = 15_000  # SPAs may never reach true idle
_FINAL_TIMEOUT = 60_000


def _trace(msg: str) -> None:
    print(f"[warmup] {msg}", flush=True)


def _get_app_frame(page):
    for f in page.frames:
        if "/~/+" in f.url:
            return f
    return page


def warmup(
    url: str,
    password: str | None = None,
    max_retries: int = 3,
) -> None:
    pw = password or os.getenv("ADMIN_PASSWORD", "custodoce123")
    _trace(f"warming {url} (max_retries={max_retries})")

    for attempt in range(max_retries):
        _trace(f"attempt {attempt + 1}/{max_retries}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/120",
            )
            page = ctx.new_page()

            try:
                _trace("navigating...")
                page.goto(url, timeout=120_000)
                page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT)
                page.wait_for_timeout(3000)
                _trace(f"loaded, title={page.title()}")

                app = _get_app_frame(page)
                _trace(f"app frame: {app.url}")

                for _ in range(10):
                    pw_input = app.locator("input[type='password']").first
                    if pw_input.count() > 0 and pw_input.is_visible():
                        _trace("password gate detected, logging in...")
                        pw_input.fill(pw)
                        entrar = app.locator("button:has-text('Entrar')")
                        if entrar.count() > 0:
                            entrar.first.click()
                            page.wait_for_timeout(3000)
                            page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT)
                            page.wait_for_timeout(3000)
                            app = _get_app_frame(page)
                        break
                    time.sleep(2)
                else:
                    _trace("no password gate found")

                for _ in range(15):
                    sleep_dialog = app.locator("text=gone to sleep")
                    if sleep_dialog.count() > 0 and sleep_dialog.first.is_visible():
                        _trace("app hibernando, acordando...")
                        wake_btn = app.locator("button:has-text('get this app back up')")
                        if wake_btn.count() > 0:
                            wake_btn.first.click()
                            page.wait_for_timeout(5000)
                            page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT)
                            page.wait_for_timeout(5000)
                            app = _get_app_frame(page)
                        break

                    app = _get_app_frame(page)
                    btn = app.locator("button:has-text('Visao Geral')")
                    if btn.count() > 0 and btn.first.is_visible():
                        _trace("sidebar pronta!")
                        browser.close()
                        return
                    time.sleep(5)
                else:
                    _trace("app nao respondeu (sidebar nao apareceu)")

                app = _get_app_frame(page)
                btn = app.locator("button:has-text('Visao Geral')")
                if btn.count() > 0 and btn.first.is_visible():
                    _trace("sidebar pronta (final check)!")
                    browser.close()
                    return

                _trace("fechando browser (app nao respondeu)")
                browser.close()
            except Exception as e:
                _trace(f"erro: {e}")
                browser.close()

        if attempt < max_retries - 1:
            _trace("aguardando 20s antes de retentar...")
            time.sleep(20)

    _trace(f"warmup falhou apos {max_retries} tentativas")
    sys.exit(1)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://custodoce.streamlit.app"
    password = sys.argv[2] if len(sys.argv) > 2 else None
    retries = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    warmup(url, password, retries)
