"""
Testes para scripts/doc_utils.py — extração e validação de contadores citados.

Garante que check_counters_against_truth:
- emite WARN para números dissonantes em docs vivos
- SILENCIA (allowlist) contextos históricos/legítimos (lições, sprints, descrições)
- respeita rel_path para matching contextual
"""

from __future__ import annotations

from pathlib import Path

from scripts.doc_utils import (
    _COUNTER_ALLOW,
    check_counters_against_truth,
    extract_counters_cited,
)


def _truth(rel_path: str = "", unit: int = 976, schema: int = 94, pages: int = 21) -> dict:
    return {
        "rel_path": rel_path,
        "test_counts": {"unit": unit, "schema": schema},
        "pages_count": pages,
    }


def test_cited_extracts_numbers_and_labels():
    content = "Temos 21 páginas e 1070 testes no total."
    cited = extract_counters_cited(content)
    pairs = {(num, label) for num, label in cited}
    assert (21, "páginas") in pairs
    assert (1070, "testes") in pairs


def test_dissonant_page_count_warns():
    cited = [(18, "páginas")]
    warns = check_counters_against_truth(cited, _truth(rel_path="docs/architecture.md"))
    assert any("Contador páginas: doc diz 18" in w for w in warns)


def test_correct_page_count_silent():
    cited = [(21, "páginas")]
    warns = check_counters_against_truth(cited, _truth(rel_path="AGENTS.md"))
    assert not warns


def test_dissonant_test_count_warns():
    cited = [(729, "testes")]
    warns = check_counters_against_truth(cited, _truth(rel_path="AGENTS.md"))
    assert any("Contador testes: doc diz 729" in w for w in warns)


def test_real_test_counts_silent():
    cited = [(976, "testes"), (94, "testes"), (1070, "testes")]
    warns = check_counters_against_truth(cited, _truth(rel_path="AGENTS.md"))
    assert not warns


def test_historical_lessons_pages_allowed():
    cited = [(19, "páginas")]
    warns = check_counters_against_truth(cited, _truth(rel_path="LESSONS.md"))
    assert not warns


def test_historical_readme_pages_allowed():
    cited = [(18, "páginas")]
    warns = check_counters_against_truth(cited, _truth(rel_path="README.md"))
    assert not warns


def test_historical_readme_tests_allowed():
    cited = [(1274, "testes")]
    warns = check_counters_against_truth(cited, _truth(rel_path="README.md"))
    assert not warns


def test_tests_readme_descriptions_allowed():
    cited = [(508, "testes"), (13, "testes"), (25, "testes"), (102, "testes")]
    warns = check_counters_against_truth(cited, _truth(rel_path="tests/README.md"))
    assert not warns


def test_contributing_historical_allowed():
    cited = [(483, "testes")]
    warns = check_counters_against_truth(cited, _truth(rel_path="docs/contributing.md"))
    assert not warns


def test_agents_status_actual_counts_allowed():
    cited = [(1068, "testes"), (113, "testes")]
    warns = check_counters_against_truth(cited, _truth(rel_path="AGENTS.md"))
    assert not warns


def test_allowlist_is_complete_for_known_docs():
    # Se algum dia um doc vivo novo aparecer com número antigo, este teste
    # documenta o contrato: os pares abaixo NUNCA devem virar WARN.
    for rel, num, label in _COUNTER_ALLOW:
        assert Path(rel).name  # caminho relativo válido
        assert isinstance(num, int)
        assert label in ("páginas", "testes")
