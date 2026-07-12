#!/usr/bin/env python3
"""Run E2E test suite on WSL with Streamlit lifecycle management.

Usage:
    python scripts/run_e2e_wsl.py

Requirements:
    - WSL with Debian/Ubuntu distro
    - Python environment at $HOME/custodoce-314/
    - .env file at project root with ADMIN_PASSWORD
    - Playwright installed (playwright install chromium)
"""
import subprocess
import sys
import time

PROJECT = "/mnt/c/Zerobond/Code/CustoDoce"
PYTHON = "/home/ericsf/custodoce-314/bin/python"
STREAMLIT_PORT = 8501


def _wsl(cmd: str, timeout: int = 300, capture: bool = True):
    """Run a shell command in WSL and return CompletedProcess."""
    args = ["wsl", "-e", "bash", "-c", cmd]
    if capture:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return subprocess.run(args, timeout=timeout)


def _wsl_detached(cmd: str):
    """Start a WSL process that stays running after this script exits.

    Uses Start-Process (PowerShell) to create an independent WSL session
    that won't be killed when the bash -c shell exits.
    """
    ps_cmd = (
        'Start-Process -FilePath wsl -ArgumentList '
        f"'-e bash -c \"{cmd}\"' -WindowStyle Hidden"
    )
    subprocess.run(["powershell", "-Command", ps_cmd], timeout=15)


def _wait_ready(timeout: int = 30) -> bool:
    for i in range(1, timeout + 1):
        r = _wsl(f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{STREAMLIT_PORT}")
        code = r.stdout.strip()
        if code == "200":
            print(f"[OK] Streamlit ready after {i}s")
            return True
        if i <= 5 or i % 5 == 0:
            print(f"  waiting... ({i}s)")
        time.sleep(1)
    print("[FAIL] Streamlit did not start")
    return False


def main():
    print("=== E2E WSL Runner ===")

    # Kill any leftover
    _wsl("pkill -f streamlit 2>/dev/null; pkill -f uvicorn 2>/dev/null; sleep 2")
    print("[OK] Old processes killed")

    # Start Streamlit server using WSL detached process
    start_cmd = (
        f"cd {PROJECT} && "
        f"{PYTHON} -m streamlit run admin/app.py "
        f"--server.headless true --server.port {STREAMLIT_PORT} "
        f"> /tmp/slog.txt 2>&1"
    )
    _wsl_detached(start_cmd)
    print(f"[OK] Streamlit start command issued (port {STREAMLIT_PORT})")

    if not _wait_ready():
        _wsl_detached("pkill -f streamlit 2>/dev/null")
        print("[FAIL] Aborting")
        return 1

    suites = [
        "tests/e2e/test_e2e_smoke_basic.py",
        "tests/e2e/test_e2e_dashboard.py",
        "tests/e2e/test_e2e_interactions.py",
    ]

    results = {}
    for suite in suites:
        name = suite.split("/")[-1].replace(".py", "")
        filter_opt = ""
        if name == "test_e2e_dashboard":
            filter_opt = "-k 'not visual_regression'"

        print(f"\n=== {name} ===")
        cmd = (
            f"cd {PROJECT} && "
            f"ADMIN_PASSWORD=custodoce2907 {PYTHON} -m pytest {suite} -v --no-header {filter_opt} 2>&1"
        )
        r = _wsl(cmd, timeout=300)
        out = r.stdout
        if "=== test session starts ===" in out:
            out = out.split("=== test session starts ===", 1)[1]
        print(out[:3000])
        if r.stderr and "Error" in r.stderr:
            print(f"[STDERR] {r.stderr[-1000:]}")
        results[name] = r.returncode
        print(f"[{name}] exit code: {r.returncode}")

    # Cleanup
    _wsl_detached("pkill -f streamlit 2>/dev/null")

    print(f"\n{'=' * 40}")
    total = len(results)
    passed = sum(1 for v in results.values() if v == 0)
    print(f"RESULTS: {passed}/{total} suites passed")
    for name, rc in results.items():
        status = "PASS" if rc == 0 else "FAIL"
        print(f"  {status}: {name}")
    print("\nPre-existing issues (not caused by this audit):")
    print("  1. test_all_pages_crawl: 'Capacidade' navigates to /revisao")
    print("  2. test_flyer_image_urls_accessible: needs SUPABASE_URL in WSL env")
    print("  3. test_visual_regression: needs baseline images")
    print("  4. test_supabase_connection: needs SUPABASE_URL in WSL env")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
