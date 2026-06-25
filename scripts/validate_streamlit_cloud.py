"""Simple HTTP health check for Streamlit Cloud app."""
import os
import sys
import urllib.request
import urllib.error

APP_URL = os.environ.get("STREAMLIT_APP_URL", "https://custodoce.streamlit.app")


def check_app() -> int:
    print(f"Verificando {APP_URL}...")
    try:
        r = urllib.request.urlopen(APP_URL, timeout=30)  # noqa: S310 - URL controlada via env var
        body = r.read().decode("utf-8", errors="replace")
        if r.status < 500 and "CustoDoce" in body:
            print("OK - App online")
            return 0
        print("FALHA - App offline ou sem conteudo esperado")
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
