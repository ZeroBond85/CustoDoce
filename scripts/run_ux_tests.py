#!/usr/bin/env python3
"""
CustoDoce - UX Analysis Test Runner
Executa todos os testes da matriz UX de forma orquestrada.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

class TestRunner:
    def __init__(self, verbose: bool = False, dry_run: bool = False):
        self.verbose = verbose
        self.dry_run = dry_run
        self.results: list[tuple[str, bool, str]] = []

    def run(self, cmd: list[str], cwd: Path = None, env: dict = None, timeout: int = 300) -> tuple[bool, str]:
        """Executa comando e retorna (success, output)."""
        cwd = cwd or REPO_ROOT
        env = env or os.environ.copy()

        if self.dry_run:
            print(f"[DRY-RUN] {' '.join(cmd)}")
            return True, "dry-run"

        print(f"\n{'='*60}")
        print(f"RUN: {' '.join(cmd)}")
        print(f"CWD: {cwd}")
        print(f"{'='*60}")

        try:
            result = subprocess.run(
                cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
            )
            success = result.returncode == 0
            output = result.stdout + result.stderr
            if self.verbose or not success:
                print(output)
            return success, output
        except subprocess.TimeoutExpired:
            return False, f"TIMEOUT after {timeout}s"
        except Exception as e:
            return False, str(e)

    def record(self, name: str, success: bool, output: str):
        self.results.append((name, success, output))
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"\n{status} {name}")

    def summary(self):
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}")
        passed = sum(1 for _, s, _ in self.results if s)
        total = len(self.results)
        for name, success, _ in self.results:
            status = "✅" if success else "❌"
            print(f"  {status} {name}")
        print(f"\nTotal: {passed}/{total} passed")
        return passed == total


def phase1_unit_and_lint(runner: TestRunner) -> bool:
    """Fase 1: Lint + Typecheck + Unit + Schema"""
    print("\n📦 FASE 1: Lint + Typecheck + Unit + Schema")

    # Ruff
    success, out = runner.run(["ruff", "check", "."])
    runner.record("ruff check", success, out)
    if not success:
        return False

    # MyPy
    success, out = runner.run(["python", "-m", "mypy", "."])
    runner.record("mypy", success, out)
    if not success:
        return False

    # Unit tests
    success, out = runner.run(["python", "-m", "pytest", "tests/unit/", "tests/schema/", "-q", "--tb=short"])
    runner.record("unit + schema tests", success, out)
    if not success:
        return False

    # Mock validation
    success, out = runner.run(["python", "-m", "pytest", "tests/unit/test_validate_mocks_against_manifest.py", "-q"])
    runner.record("mock validation", success, out)

    return True


def phase2_integration(runner: TestRunner) -> bool:
    """Fase 2: Integration tests (requer Supabase)"""
    print("\n🔗 FASE 2: Integration Tests")

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        print("⚠️ SUPABASE_URL/SERVICE_ROLE_KEY não configurados — pulando integration tests")
        runner.record("integration tests", True, "skipped - no credentials")
        return True

    success, out = runner.run(["python", "-m", "pytest", "tests/integration/", "-v", "--tb=short"])
    runner.record("integration tests", success, out)
    return success


def phase3_e2e_local(runner: TestRunner) -> bool:
    """Fase 3: E2E Local (requer Streamlit rodando)"""
    print("\n🌐 FASE 3: E2E Local")

    streamlit_url = os.environ.get("STREAMLIT_URL", "http://localhost:8501")

    # Verificar se Streamlit está rodando
    import requests
    try:
        resp = requests.get(streamlit_url, timeout=5)
        if resp.status_code != 200:
            print(f"⚠️ Streamlit não responde em {streamlit_url}")
            runner.record("e2e local", False, "streamlit not running")
            return False
    except Exception as e:
        print(f"⚠️ Streamlit não acessível: {e}")
        runner.record("e2e local", False, f"streamlit not accessible: {e}")
        return False

    env = os.environ.copy()
    env["STREAMLIT_URL"] = streamlit_url

    # Smoke test básico
    success, out = runner.run(
        ["python", "-m", "pytest", "tests/e2e/test_e2e_smoke_basic.py", "-v"],
        env=env, timeout=120
    )
    runner.record("e2e smoke", success, out)
    if not success:
        return False

    # Navegação completa (21 páginas)
    success, out = runner.run(
        ["python", "-m", "pytest", "tests/e2e/test_e2e_dashboard.py", "-v", "-k", "not visual"],
        env=env, timeout=300
    )
    runner.record("e2e navigation (21 pages)", success, out)
    if not success:
        return False

    # Interações específicas
    success, out = runner.run(
        ["python", "-m", "pytest", "tests/e2e/test_e2e_interactions.py", "-v"],
        env=env, timeout=300
    )
    runner.record("e2e interactions", success, out)

    # Supabase data checks
    success, out = runner.run(
        ["python", "-m", "pytest", "tests/e2e/test_e2e_dashboard.py::test_supabase_connection", "-v"],
        env=env, timeout=60
    )
    runner.record("e2e supabase checks", success, out)

    return True


def phase4_visual_regression(runner: TestRunner, update_baselines: bool = False) -> bool:
    """Fase 4: Visual Regression"""
    print("\n🎨 FASE 4: Visual Regression")

    streamlit_url = os.environ.get("STREAMLIT_URL", "http://localhost:8501")
    env = os.environ.copy()
    env["STREAMLIT_URL"] = streamlit_url
    if update_baselines:
        env["UPDATE_BASELINES"] = "1"

    success, out = runner.run(
        ["python", "-m", "pytest", "tests/e2e/test_e2e_dashboard.py::test_visual_regression", "-v"],
        env=env, timeout=300
    )
    runner.record("visual regression", success, out)
    return success


def phase5_accessibility(runner: TestRunner) -> bool:
    """Fase 5: Acessibilidade (axe-core)"""
    print("\n♿ FASE 5: Acessibilidade")

    # Verificar se axe-selenium está instalado
    try:
        import axe_selenium_python  # noqa
    except ImportError:
        print("⚠️ axe-selenium-python não instalado — pulando")
        runner.record("a11y audit", True, "skipped - axe not installed")
        return True

    streamlit_url = os.environ.get("STREAMLIT_URL", "http://localhost:8501")
    env = os.environ.copy()
    env["STREAMLIT_URL"] = streamlit_url

    # Criar pasta de testes a11y se não existir
    a11y_dir = REPO_ROOT / "tests" / "a11y"
    a11y_dir.mkdir(parents=True, exist_ok=True)

    # Test script básico
    test_file = a11y_dir / "test_a11y_basic.py"
    if not test_file.exists():
        test_file.write_text('''
import pytest
from axe_selenium_python import Axe
from tests.e2e.conftest import logged_in_app_and_page_local

@pytest.mark.a11y
def test_a11y_visao_geral(logged_in_app_and_page_local):
    app, page = logged_in_app_and_page_local
    axe = Axe(app)
    axe.inject()
    results = axe.run()
    assert len(results["violations"]) == 0, f"Violações: {results['violations']}'

@pytest.mark.a11y
def test_a11y_precos(logged_in_app_and_page_local):
    app, page = logged_in_app_and_page_local
    # Navegar para Preços
    page.click("text=Preços")
    page.wait_for_timeout(2000)
    axe = Axe(app)
    axe.inject()
    results = axe.run()
    assert len(results["violations"]) == 0, f"Violações: {results['violations']}'

# Adicionar mais páginas conforme necessário
''')

    success, out = runner.run(
        ["python", "-m", "pytest", "tests/a11y/", "-v", "--tb=short"],
        env=env, timeout=180
    )
    runner.record("a11y audit", success, out)
    return success


def phase6_performance(runner: TestRunner) -> bool:
    """Fase 6: Performance (Lighthouse CI)"""
    print("\n⚡ FASE 6: Performance")

    streamlit_url = os.environ.get("STREAMLIT_URL", "http://localhost:8501")

    # Verificar lighthouse
    try:
        subprocess.run(["npx", "lighthouse", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️ Lighthouse CI não instalado — pulando")
        runner.record("lighthouse", True, "skipped - lighthouse not installed")
        return True

    success, out = runner.run(
        ["npx", "lighthouse", streamlit_url, "--output=json", "--output-path=./lighthouse.json", "--chrome-flags=--headless"],
        timeout=120
    )
    runner.record("lighthouse", success, out)

    if success:
        # Parse resultados
        import json
        try:
            with open("lighthouse.json") as f:
                data = json.load(f)
            categories = data.get("categories", {})
            perf = categories.get("performance", {}).get("score", 0) * 100
            a11y = categories.get("accessibility", {}).get("score", 0) * 100
            bp = categories.get("best-practices", {}).get("score", 0) * 100
            seo = categories.get("seo", {}).get("score", 0) * 100
            print("\n📊 Lighthouse Scores:")
            print(f"  Performance: {perf:.0f}/100")
            print(f"  Accessibility: {a11y:.0f}/100")
            print(f"  Best Practices: {bp:.0f}/100")
            print(f"  SEO: {seo:.0f}/100")

            if perf < 90:
                print("⚠️ Performance < 90 - revisar")
        except Exception:
            pass

    return success


def phase7_capacity(runner: TestRunner) -> bool:
    """Fase 7: Capacity Planning Check"""
    print("\n📊 FASE 7: Capacity Planning")

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        print("⚠️ Supabase não configurado — pulando")
        runner.record("capacity check", True, "skipped - no credentials")
        return True

    # Executar script de capacity
    success, out = runner.run(["python", "-c", """
from dashboard.pages.capacity_planning import render_capacity_planning
render_capacity_planning()
"""])
    runner.record("capacity check", success, out)
    return success


def phase8_diagnostics(runner: TestRunner) -> bool:
    """Fase 8: Diagnostics (slow tests)"""
    print("\n🔬 FASE 8: Diagnostics")

    success, out = runner.run(["python", "-m", "pytest", "tests/diagnostics/", "-v", "-m", "slow", "--tb=short"])
    runner.record("diagnostics", success, out)
    return success


def main():
    parser = argparse.ArgumentParser(description="CustoDoce UX Test Runner")
    parser.add_argument("--phase", type=int, choices=range(1, 9), help="Run specific phase (1-8)")
    parser.add_argument("--all", action="store_true", help="Run all phases")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without executing")
    parser.add_argument("--update-baselines", action="store_true", help="Update visual regression baselines")
    args = parser.parse_args()

    runner = TestRunner(verbose=args.verbose, dry_run=args.dry_run)

    phases = {
        1: ("Lint + Typecheck + Unit", lambda: phase1_unit_and_lint(runner)),
        2: ("Integration", lambda: phase2_integration(runner)),
        3: ("E2E Local", lambda: phase3_e2e_local(runner)),
        4: ("Visual Regression", lambda: phase4_visual_regression(runner, args.update_baselines)),
        5: ("Accessibility", lambda: phase5_accessibility(runner)),
        6: ("Performance (Lighthouse)", lambda: phase6_performance(runner)),
        7: ("Capacity Planning", lambda: phase7_capacity(runner)),
        8: ("Diagnostics", lambda: phase8_diagnostics(runner)),
    }

    if args.phase:
        phases_to_run = {args.phase: phases[args.phase]}
    elif args.all:
        phases_to_run = phases
    else:
        # Default: phases 1-3 (core)
        phases_to_run = {1: phases[1], 2: phases[2], 3: phases[3]}

    print(f"\n{'='*60}")
    print("CUSTODOCE UX TEST RUNNER")
    print(f"{'='*60}")
    print(f"Phases to run: {list(phases_to_run.keys())}")
    print(f"Repo: {REPO_ROOT}")

    all_passed = True
    for phase_num, (name, fn) in phases_to_run.items():
        print(f"\n{'🔄'*20}")
        print(f"PHASE {phase_num}: {name}")
        print(f"{'🔄'*20}")
        try:
            passed = fn()
            all_passed = all_passed and passed
        except KeyboardInterrupt:
            print("\n⏹️ Interrupted by user")
            all_passed = False
            break
        except Exception as e:
            print(f"\n💥 Phase {phase_num} crashed: {e}")
            runner.record(f"phase_{phase_num}", False, str(e))
            all_passed = False

    success = runner.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()