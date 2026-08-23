"""Comprehensive production validation — sem browser, sem psycopg2.

Audit item #3 / regra AGENTS #4: TODAS as checagens de DB vão via RPC
`exec_sql_query` (porta 443), reutilizando as queries bulk estáticas de
validate_db_schema.py. Seções HTTP (Streamlit Cloud / GitHub Actions)
preservadas. Substitui o path legado psycopg2:5432 (bloqueado no CI).

Uso:
    python scripts/validate_production.py
"""

import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.validate_db_schema import (  # noqa: E402
    SQL_COLUMNS,
    SQL_FUNCTIONS,
    _safe_set,
    get_client,
    load_manifest,
    run_query,
)

# Funções RPC esperadas em produção (constantes — nomes controlados pelo repo).
PROD_EXPECTED_FUNCTIONS = [
    "upsert_price_rpc",
    "cleanup_old_prices",
    "cleanup_old_logs",
    "cleanup_old_flyers",
    "update_history_from_prices",
    "exec_sql",
]

# Smoke tests como literais estáticos (SELECT-only, aceitos pelo RPC 443).
SMOKE_QUERIES = (
    ("exec_sql('SELECT 1') works", "SELECT exec_sql('SELECT 1')"),
    ("cleanup_old_prices(0) callable", "SELECT cleanup_old_prices(0)"),
    ("cleanup_old_logs(0) callable", "SELECT cleanup_old_logs(0)"),
    ("cleanup_old_flyers(0) callable", "SELECT cleanup_old_flyers(0)"),
)

REPO_URL = "https://api.github.com/repos/ZeroBond85/CustoDoce/actions/workflows"

results = {"pass": 0, "fail": 0, "items": []}


def check(name, ok, detail=""):
    if ok:
        results["pass"] += 1
        status = "PASS"
    else:
        results["fail"] += 1
        status = "FAIL"
    results["items"].append(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def _group_columns(rows):
    cols_by_table: dict[str, set] = {}
    for row in rows or []:
        cols_by_table.setdefault(row["table_name"], set()).add(row["col"])
    return cols_by_table


def db_checks():
    """Schema + funções + smoke via RPC exec_sql_query (porta 443)."""
    print("\n=== 1. DB Schema (RPC 443) ===")
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        check("DB checks", True, "skipped (SUPABASE_URL/SERVICE_ROLE_KEY ausentes)")
        return

    client = get_client()
    manifest = load_manifest()

    rows = run_query(client, SQL_COLUMNS)
    if rows is None:
        check("DB reachable via exec_sql_query", False, "ver log acima")
        return
    check("DB reachable via exec_sql_query", True)

    cols_by_table = _group_columns(rows)
    for table, spec in sorted(manifest.items()):
        expected = set(spec.get("columns", []))
        existing = cols_by_table.get(table)
        if existing is None:
            check(f"Table {table}", False, "tabela ausente no schema public")
            continue
        missing = expected - existing
        extra = existing - expected
        check(
            f"Table {table}: {len(expected)} expected, {len(existing)} actual",
            not missing,
            f"missing={sorted(missing)}" if missing else "OK",
        )
        if extra:
            print(f"       (extra cols: {sorted(extra)})")

    # ─── 2. RPC functions ───
    print("\n=== 2. RPC Functions ===")
    fns = _safe_set(client, SQL_FUNCTIONS)
    for fn in PROD_EXPECTED_FUNCTIONS:
        check(f"Function {fn}()", bool(fns) and fn in fns)

    # ─── 3. Smoke: chamadas SELECT-only via RPC ───
    print("\n=== 3. RPC Execution Test ===")
    for name, sql in SMOKE_QUERIES:
        ok = run_query(client, sql) is not None
        check(name, ok)


def http_checks():
    """Streamlit Cloud + GitHub Actions (inalterado do legado)."""
    print("\n=== 4. Streamlit Cloud ===")
    try:
        r = httpx.get("https://custodoce.streamlit.app", follow_redirects=False, timeout=30)
        ok = r.status_code in (200, 301, 302, 303, 307)
        check(
            f"App URL: HTTP {r.status_code}",
            ok,
            "auth redirect (expected without browser session)" if r.status_code == 303 else "",
        )
    except Exception as e:
        check("App URL reachable", False, str(e)[:80])

    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    for section, workflow in (("5. GitHub Actions CI", "ci.yml"), ("6. Scrape Workflow", "scrape.yml")):
        print(f"\n=== {section} ===")
        if not token:
            check(f"{workflow} status", True, "skipped (GITHUB_TOKEN not set locally)")
            continue
        try:
            r = httpx.get(f"{REPO_URL}/{workflow}/runs?per_page=1&status=completed", headers=headers, timeout=15)
            if r.status_code == 200:
                runs = r.json().get("workflow_runs", [])
                if runs:
                    last = runs[0]
                    check(
                        f"{workflow} latest run #{last['run_number']}: {last['conclusion']}",
                        last.get("conclusion") == "success",
                        f"branch={last.get('head_branch')}",
                    )
                else:
                    check(f"{workflow} runs found", False, "no completed runs")
            else:
                check(f"{workflow} API", False, f"HTTP {r.status_code} — {r.text[:100]}")
        except Exception as e:
            check(f"{workflow} API reachable", False, str(e)[:80])


def main():
    db_checks()
    http_checks()

    print(f"\n{'=' * 50}")
    print(f"Results: {results['pass']} PASS, {results['fail']} FAIL")
    for item in results["items"]:
        print(item)

    sys.exit(0 if results["fail"] == 0 else 1)


if __name__ == "__main__":
    sys.exit(main())
