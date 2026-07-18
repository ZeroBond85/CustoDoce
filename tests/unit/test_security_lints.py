"""Regression tests for security audit fixes (findings F-01, F-02, F-04, F-11, F-13).

These run offline (no DB, no secrets) and guard against reintroduction of the
security gaps flagged in the audit. They replace the previous `continue-on-error:
true` masking in ci.yml (AGENTS.md rule #11).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def test_scrape_requests_rls_migration_exists():
    # F-01: dedicated RLS migration must exist and enable RLS on scrape_requests
    mig = REPO / "supabase" / "011_scrape_requests_rls.sql"
    assert mig.exists(), "011_scrape_requests_rls.sql missing (F-01)"
    text = mig.read_text(encoding="utf-8")
    assert "ALTER TABLE scrape_requests ENABLE ROW LEVEL SECURITY" in text
    assert "CREATE POLICY" in text


def test_consolidated_includes_rls_migration():
    # F-01: generate_consolidated() must wire the new migration in
    deploy = REPO / "scripts" / "deploy_database.py"
    text = deploy.read_text(encoding="utf-8")
    assert "011_scrape_requests_rls.sql" in text, "generate_consolidated missing PHASE 26 (F-01)"


def test_no_insecure_exec_sql_definition():
    # F-04: consolidated must NOT define exec_sql/exec_sql_query without SET search_path
    consolidated = REPO / "supabase" / "consolidated_migration.sql"
    text = consolidated.read_text(encoding="utf-8")
    # Find every CREATE OR REPLACE FUNCTION exec_sql... block
    for m in re.finditer(
        r"CREATE OR REPLACE FUNCTION (exec_sql|exec_sql_query)\b.*?AS \$\$;",
        text,
        re.DOTALL,
    ):
        block = m.group(0)
        assert "SET search_path" in block, f"Insecure RPC definition lacks SET search_path:\n{block[:200]}"


def test_openpyxl_is_pinned():
    # F-13: openpyxl must not be left floating in requirements.txt
    reqs = (REPO / "requirements.txt").read_text(encoding="utf-8")
    for line in reqs.splitlines():
        if line.strip().startswith("openpyxl"):
            assert re.search(r">=|==", line), f"openpyxl not pinned: {line!r}"
            return
    raise AssertionError("openpyxl not present in requirements.txt")


def test_workflows_have_top_level_permissions():
    # F-11: every workflow must declare least-privilege top-level permissions
    wf_dir = REPO / ".github" / "workflows"
    for wf in sorted(wf_dir.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        # parse first-level 'permissions:' that is not indented
        assert re.search(r"(?m)^permissions:", text), f"{wf.name} missing top-level permissions:"


def test_test_store_recovery_no_direct_input_interpolation():
    # F-02: workflow_run steps must not interpolate inputs.stores directly in run:
    wf = REPO / ".github" / "workflows" / "test_store_recovery.yml"
    text = wf.read_text(encoding="utf-8")
    # Allow env: STORES_INPUT: ${{ github.event.inputs.stores }} but forbid
    # run: ... "${{ github.event.inputs.stores }}" interpolation.
    assert "STORES_INPUT: ${{ github.event.inputs.stores }}" in text
    assert '"${{ github.event.inputs.stores }}"' not in text, "Direct input interpolation in run: (F-02)"


def test_verify_false_removed_from_discover_urls():
    # A-03: no TLS verification disabled
    discover = REPO / "scripts" / "discover_urls.py"
    text = discover.read_text(encoding="utf-8")
    assert "verify=False" not in text, "discover_urls.py must not disable TLS verification (A-03)"
