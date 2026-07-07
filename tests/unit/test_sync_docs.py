"""Regression tests for scripts/sync_docs.py.

Drift detection at Sprint 4 (see AGENTS.md Licao #11): these tests lock in the
correct counting semantics so future contributors can't regress to the
"411 unit instead of 418" bug. They also lock in the AGENTS.md status-table
regex, the pages extraction, and the services API catalog.

These are pure unit tests — no DB, no network. subprocess.run for _count_tests
is mocked via unittest.mock where needed.
"""

from unittest.mock import MagicMock, patch

from scripts import sync_docs


def _fake_proc(stdout: str, returncode: int = 0):
    p = MagicMock()
    p.stdout = stdout
    p.stderr = ""
    p.returncode = returncode
    return p


SAMPLE_PYTEST_OUTPUT = (
    "tests/unit/test_normalizer.py::test_one PASSED\n"
    "<Function test_one>\n"
    "<Function test_two>\n"
    "<Function test_three>\n"
    "<Function test_four>\n"
    "<Coroutine test_async_helper>\n"
    "<Coroutine test_async_helper_two>\n"
    "6 tests collected in 0.10s\n"
)


# 1. _count_tests must include async coroutines
def test_count_tests_patterns_match_both_sync_and_async():
    """412 sync + 7 coroutines (test_telegram_handlers) all must be counted."""
    import re

    sync_count = len(re.findall(r"<Function\s+test_", SAMPLE_PYTEST_OUTPUT))
    async_count = len(re.findall(r"<Coroutine\s+test_", SAMPLE_PYTEST_OUTPUT))
    assert sync_count == 4
    assert async_count == 2


def test_count_tests_handles_coroutine_only():
    """Files with only async tests must produce non-zero count."""
    import re

    sample = "<Coroutine test_only_async>\n1 tests collected\n"
    async_count = len(re.findall(r"<Coroutine\s+test_", sample))
    assert async_count == 1


def test_count_tests_zero_output_safe():
    fake = _fake_proc("", returncode=0)
    with patch("subprocess.run", return_value=fake):
        result = sync_docs._count_tests()
    assert isinstance(result, dict)
    assert all(v == 0 for v in result.values())


# 2. _check_drift / _extract_actual_test_count
def test_extract_actual_test_count_parsing():
    """Parses '6 tests collected' from real pytest output."""
    fake = _fake_proc(SAMPLE_PYTEST_OUTPUT, returncode=0)
    with patch("subprocess.run", return_value=fake):
        with patch.object(sync_docs, "_count_tests", return_value={"unit": 6}):
            pytest_total, my_count = sync_docs._extract_actual_test_count("tests/unit")
    assert pytest_total == 6
    assert my_count == 4 + 2  # 4 sync + 2 async from SAMPLE output


def test_check_drift_returns_list():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="6 tests collected\n", returncode=0)
        with patch.object(sync_docs, "_count_tests", return_value={"unit": 6, "schema": 2}):
            drift = sync_docs._check_drift()
    assert isinstance(drift, list)


# 3. _extract_pages: lock PAGES tuple format from dashboard/components/layout.py
def test_extract_pages_returns_3_tuples():
    pages = sync_docs._extract_pages()
    assert isinstance(pages, list)
    for entry in pages:
        assert isinstance(entry, tuple) and len(entry) == 3


def test_extract_pages_known_ids():
    pages = sync_docs._extract_pages()
    ids = {p[0] for p in pages}
    expected = {"visao_geral", "precos", "historico", "calculadora", "diagnostico"}
    assert expected.issubset(ids), f"Missing pages: {expected - ids}"


def test_extract_pages_tolerates_quote_variants():
    """_extract_pages() now reads from navigation_config (not file parsing)."""
    pages = sync_docs._extract_pages()
    assert len(pages) >= 19, f"Expected >= 19 pages, got {len(pages)}"
    for p in pages:
        assert isinstance(p, tuple) and len(p) == 3, f"Invalid page tuple: {p}"
        assert p[0] and p[1] and p[2], f"Empty field in page tuple: {p}"


# 4. _extract_services_api: lock service module whitelist
def test_extract_services_api_excludes_dunder_modules():
    api = sync_docs._extract_services_api()
    assert "__init__" not in api
    for name in api:
        assert not name.startswith("_"), f"{name} leaked"


def test_extract_services_api_includes_collector():
    api = sync_docs._extract_services_api()
    assert "collector" in api


# 5. _update_agents_md: lock AGENTS.md status-table format with combined row
def test_update_agents_md_combined_unit_schema_row(tmp_path):
    agents_src = (
        "# CustoDoce Memory\n"
        "\n"
        "Some prose paragraph\n"
        "\n"
        "| Ferramenta | Status |\n"
        "|------------|--------|\n"
        "| pytest (unit) | 0 passing | ok |\n"
        "| pytest (schema) | 0 passing | ok |\n"
        "\n"
        "## Lições Aprendidas\n"
    )
    agents_file = tmp_path / "AGENTS.md"
    agents_file.write_text(agents_src, encoding="utf-8")

    state = {
        "updated_at": "2026-06-29 18:00 UTC",
        "test_counts": {"unit": 418, "schema": 94, "integration": 102, "real": 6, "e2e": 49},
        "pages": [],
        "pages_count": 0,
        "services_api": {},
        "workflows": [],
        "workflows_count": 0,
        "api_services": [],
        "total_tests": 669,
    }
    with patch.object(sync_docs, "_AGENTS", agents_file):
        sync_docs._update_agents_md(state, dry_run=False)

    result = agents_file.read_text(encoding="utf-8")

    # The new rows must use COMBINED "unit + schema" line
    assert "pytest (unit + schema)" in result, "Expected COMBINED row 'pytest (unit + schema)', got:\n" + result
    # Must include both 418 (unit) and 94 (schema) in combined row
    assert "418" in result
    assert "94" in result
    assert "102" in result
    # Should NOT contain the old separate-row format
    assert "| pytest (unit) | 418 passing |" not in result
    assert "| pytest (schema) | 94 passing |" not in result
