"""Unit tests for scripts/sync_docs_v2/ — pure unit, no I/O, fast.

Lição #25: new code = new tests. This file locks in the v2 classifier,
updater, parser, truth, and CLI behavior so refactoring doesn't regress.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.sync_docs_v2 import classifier, cli, parser, truth, updater


# ── truth.py ────────────────────────────────────────────────────────────────


def test_build_truth_keys_and_types():
    """build_truth() returns dict with all expected keys."""
    with patch("scripts.sync_docs_v2.truth.count_tests", return_value={"unit": 10, "schema": 5}):
        with patch("scripts.sync_docs_v2.truth._extract_pages", return_value=[("p1", "i", "L1")]):
            with patch("scripts.sync_docs_v2.truth._extract_services_api", return_value={"svc": ["fn"]}):
                with patch("scripts.sync_docs_v2.truth._extract_workflows", return_value=["wf1"]):
                    with patch("scripts.sync_docs_v2.truth._count_dashboard_pages", return_value=1):
                        t = truth.build_truth()

    assert set(t) == {
        "updated_at",
        "total_tests",
        "test_counts",
        "pages",
        "pages_count",
        "services_api",
        "workflows",
        "workflows_count",
        "api_services",
    }
    assert isinstance(t["updated_at"], str)
    assert t["total_tests"] == 15
    assert t["pages_count"] == 1
    assert t["api_services"] == ["svc"]


def test_count_tests_handles_missing_dir():
    """subprocess.run error returns 0 per category, no crash."""
    with patch("subprocess.run", side_effect=FileNotFoundError("no dir")):
        result = truth.count_tests()
    assert all(v == 0 for v in result.values())
    assert set(result) == {"unit", "schema", "integration", "e2e", "real"}


def test_count_tests_includes_async():
    """Both <Function test_> and <Coroutine test_> must be counted."""
    stdout = "<Function test_a>\n<Coroutine test_b>\n2 tests collected\n"
    with patch("subprocess.run", return_value=MagicMock(stdout=stdout)):
        assert truth.count_tests()["unit"] == 2


# ── parser.py ───────────────────────────────────────────────────────────────


def test_compute_section_spans_extends_to_next_heading():
    """Heading span extends to next same/higher-level heading."""
    text = "# H1\nfoo\n## H2\nbar\n# H1b\nbaz"
    spans = parser._compute_section_spans(text)
    assert spans[0] == "H1"
    assert spans[1] == "H1"
    assert spans[2] == "H1 > H2"
    assert spans[3] == "H1 > H2"
    assert spans[4] == "H1b"


def test_scan_all_md_finds_matches():
    """PATTERNS detect known stale numbers with correct heading context."""
    from scripts.sync_docs_v2.parser import PATTERNS, _compute_section_spans

    text = "# Status Atual\nTestes: 512 passing total 630\n"
    spans = _compute_section_spans(text)
    for pat, pat_name in PATTERNS:
        for m in pat.finditer(text):
            line_num = text[: m.start()].count("\n")
            heading = spans.get(line_num, "")
            assert heading == "Status Atual"
            assert pat_name in ("test_count_512", "test_count_630")


def test_scan_all_md_skips_excluded_dirs(tmp_path):
    """Directories in _SKIP_DIRS produce zero findings."""
    project = tmp_path / "project"
    (project / ".venv").mkdir(parents=True)
    (project / ".venv" / "dirty.md").write_text("418", encoding="utf-8")
    (project / "good.md").write_text("# Hi\n418\n", encoding="utf-8")

    with patch("scripts.sync_docs_v2.parser._ROOT", project):
        results = parser.scan_all_md()

    assert len(results) == 1
    assert results[0]["file"].endswith("good.md")


# ── classifier.py ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "heading,match,file,expected",
    [
        # CURRENT: heading with current-status marker
        ("Status Atual", "512 passing", "AGENTS.md", "CURRENT"),
        ("Métricas finais", "418", "RAIO_X.md", "CURRENT"),
        ("AVALIAÇÃO DE RISCOS", "383", "docs.md", "CURRENT"),
        # HISTORICAL: heading with historical marker
        ("Histórico de Versões", "512", "AGENTS.md", "HISTORICAL"),
        ("Lições Aprendidas", "418", "AGENTS.md", "HISTORICAL"),
        ("Lições", "709 total", "AGENTS.md", "HISTORICAL"),
        ("Milestone 2", "630 total", "notes.md", "HISTORICAL"),
        ("Changelog", "17→18", "changelog.md", "HISTORICAL"),
        ("Entregas confirmadas", "709 total", "RAIO_X.md", "HISTORICAL"),
        # HISTORICAL: match text overrides CURRENT heading
        ("Métricas de Sucesso", "512 em 29/06", "RAIO_X.md", "HISTORICAL"),
        # HISTORICAL: README roadmap
        ("Roadmap", "512", "README.md", "HISTORICAL"),
        # AMBIGUOUS: no marker found
        ("Section X", "418", "foo.md", "AMBIGUOUS"),
        ("Random", "630 total", "bar.md", "AMBIGUOUS"),
    ],
)
def test_classify_matrix(heading: str, match: str, file: str, expected: str):
    assert classifier.classify(heading, match, file) == expected


# ── updater.py ──────────────────────────────────────────────────────────────


def test_apply_fix_word_boundary():
    """\\bNUMBER\\b replacement preserves larger numbers like 1512."""
    text = "**512 passing** and 1512"
    result = updater.apply_fix(text, "512", "577")
    assert result == "**577 passing** and 1512"


def test_sync_file_only_touches_current(tmp_path):
    """Only CURRENT-classified findings are applied; HISTORICAL ignored."""
    f = tmp_path / "doc.md"
    f.write_text("**512** and **418** and **630**", encoding="utf-8")
    findings = [
        {"classification": "CURRENT", "pattern": "test_count_512", "file": "doc.md", "line": 1},
        {"classification": "HISTORICAL", "pattern": "test_count_418", "file": "doc.md", "line": 1},
        {"classification": "CURRENT", "pattern": "test_count_630", "file": "doc.md", "line": 1},
    ]
    truth_data = {
        "total_tests": 745,
        "test_counts": {"unit": 483, "schema": 94},
        "pages_count": 18,
    }
    changes = updater.sync_file(f, findings, truth_data, dry_run=False)
    assert len(changes) == 2
    content = f.read_text(encoding="utf-8")
    assert "577" in content
    assert "418" in content  # HISTORICAL preserved
    assert "745" in content


def test_sync_file_dry_run_does_not_write(tmp_path):
    """dry_run=True parses but does not modify the file."""
    f = tmp_path / "doc.md"
    original = "**512** passing"
    f.write_text(original, encoding="utf-8")
    findings = [
        {"classification": "CURRENT", "pattern": "test_count_512", "file": "doc.md", "line": 1},
    ]
    truth_data = {
        "total_tests": 745,
        "test_counts": {"unit": 483, "schema": 94},
        "pages_count": 18,
    }
    changes = updater.sync_file(f, findings, truth_data, dry_run=True)
    assert len(changes) == 1
    assert f.read_text(encoding="utf-8") == original


# ── cli.py ──────────────────────────────────────────────────────────────────


def test_cli_dump_truth_prints_json(capsys):
    """--dump-truth outputs JSON with expected content."""
    with patch("scripts.sync_docs_v2.cli.build_truth", return_value={"total_tests": 42}):
        rc = cli.main(["--dump-truth"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"total_tests": 42' in out


def test_cli_analyze_exit_code(capsys):
    """--analyze returns 0 and prints summary header."""
    with patch("scripts.sync_docs_v2.cli.scan_all_md", return_value=[]):
        rc = cli.main(["--analyze"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Total:" in out


def test_cli_sync_no_changes(capsys):
    """--sync with no CURRENT findings prints 'No stale' message."""
    with patch("scripts.sync_docs_v2.cli.scan_all_md", return_value=[]):
        with patch(
            "scripts.sync_docs_v2.cli.build_truth",
            return_value={"total_tests": 745, "test_counts": {"unit": 483, "schema": 94}, "pages_count": 18},
        ):
            rc = cli.main(["--sync"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No stale CURRENT refs found" in out
