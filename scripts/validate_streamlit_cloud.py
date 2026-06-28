"""Simple HTTP health check for Streamlit Cloud app.

Streamlit Cloud free tier goes to sleep after inactivity.
The first request (to any URL) wakes it up.
We do a warm-up request first, then check the actual app.
"""

import os
import sys
import time
import urllib.request
import urllib.error

APP_URL = os.environ.get("STREAMLIT_APP_URL", "https://custodoce.streamlit.app")


def _fetch(url: str, timeout: int = 30):
    req = urllib.request.Request(url, method="GET")  # noqa: S310 - URL controlada via env var HTTPS
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - URL controlada via env var HTTPS


def check_app() -> int:
    # 1. Warm-up: Streamlit Cloud free tier dorme após inatividade
    print(f"Warm-up: {APP_URL} ...", end=" ", flush=True)
    try:
        _fetch(APP_URL, timeout=60)
        print("OK")
    except Exception:
        print("(timeout normal, app estava dormindo)")

    # 2. Aguarda app iniciar
    time.sleep(2)

    # 3. Verificação real
    print(f"Verificando {APP_URL}...")
    try:
        r = _fetch(APP_URL, timeout=30)
        body = r.read().decode("utf-8", errors="replace")
        # Streamlit Cloud sempre retorna 303 (redirect), mesmo quando acordado
        if r.status == 303 or (r.status < 500 and "CustoDoce" in body):
            print(f"OK - App online (HTTP {r.status})")
            return 0
        print(f"FALHA - HTTP {r.status} sem conteudo esperado")
        return 1
    except urllib.error.HTTPError as e:
        if e.code < 500:
            print(f"OK - App respondeu HTTP {e.code}")
            return 0
        print(f"FALHA - HTTP {e.code}")
        return 1
    except urllib.error.URLError as e:
        print(f"FALHA - URL error: {e.reason}")
        return 1
    except Exception as e:
        print(f"FALHA - {e}")
        return 1


if __name__ == "__main__":
    sys.exit(check_app())
