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


def _truth(rel_path: str = "", unit: int = 1400, schema: int = 94, pages: int = 21) -> dict:
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
    cited = [(1400, "testes"), (94, "testes"), (1494, "testes")]
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
    # AGENTS.md Status Atual: 1400 total (unit+schema) passa direto; 115 é
    # integration (separado do total) e 4 diagnostics — ambos allowlistados.
    cited = [(1400, "passing"), (115, "passing"), (4, "passing")]
    warns = check_counters_against_truth(cited, _truth(rel_path="AGENTS.md"))
    assert not warns


def test_allowlist_is_complete_for_known_docs():
    # Se algum dia um doc vivo novo aparecer com número antigo, este teste
    # documenta o contrato: os pares abaixo NUNCA devem virar WARN.
    for rel, num, label in _COUNTER_ALLOW:
        assert Path(rel).name  # caminho relativo válido
        assert isinstance(num, int)
        assert label in ("páginas", "testes")


# ── Cache de test counts (doc_utils) ──────────────────────────────

from scripts.doc_utils import (  # noqa: E402
    _COUNTS_MEMO,
    _FULL_COUNTS_MEMO,
    _hash_test_state,
    count_tests_full_cached,
)


def test_hash_nao_inclui_git_head(tmp_path, monkeypatch):
    """Regressão Fase 1: mudar o HEAD não invalida o cache de test counts.

    Após `git commit` o HEAD muda mas os arquivos de tests/ não são tocados;
    o cache precisa sobreviver entre pre-commit e pre-push (senão pytest
    --collect-only re-roda a cada push).
    """
    # Cria estrutura mínima de tests/ para o hash não depender do repo real
    d = tmp_path / "tests" / "unit"
    d.mkdir(parents=True)
    (d / "dummy.py").write_text("# dummy\n", encoding="utf-8")

    # Chama _hash_test_state duas vezes — deve ser estável
    h1 = _hash_test_state(tmp_path)
    # Simula commit mudando HEAD (mockando _git_head_short)
    with monkeypatch.context() as m:
        m.setattr("scripts.doc_utils._git_head_short", lambda _: "abc123")
        h2 = _hash_test_state(tmp_path)
    assert h1 == h2, "Hash não deve mudar quando só HEAD muda"


def test_memo_count_tests_cached_reusa_em_duas_chamadas(tmp_path):
    """Memo in-processo evita rodar pytest_func 2x na mesma execução."""
    from scripts.doc_utils import count_tests_cached, _COUNTS_MEMO

    _COUNTS_MEMO.clear()

    calls = {"count": 0}

    def fake_pytest():
        calls["count"] += 1
        return {"unit": 100, "schema": 10, "integration": 5}

    # Cria estrutura mínima
    d = tmp_path / "tests" / "unit"
    d.mkdir(parents=True)
    (d / "dummy.py").write_text("# dummy\n", encoding="utf-8")

    r1 = count_tests_cached(tmp_path, fake_pytest)
    r2 = count_tests_cached(tmp_path, fake_pytest)

    assert r1 == r2
    assert calls["count"] == 1, "pytest_func deve ser chamado apenas 1x"


def test_memo_count_tests_full_cached_reusa_em_duas_chamadas(tmp_path):
    """Memo in-processo evita rodar pytest_func 2x na mesma execução (full)."""
    from scripts.doc_utils import count_tests_full_cached, _FULL_COUNTS_MEMO

    _FULL_COUNTS_MEMO.clear()

    calls = {"count": 0}

    def fake_pytest():
        calls["count"] += 1
        return {"unit": {"pytest_total": 1200, "my_count": 1000}}

    d = tmp_path / "tests" / "unit"
    d.mkdir(parents=True)
    (d / "dummy.py").write_text("# dummy\n", encoding="utf-8")

    r1 = count_tests_full_cached(tmp_path, fake_pytest)
    r2 = count_tests_full_cached(tmp_path, fake_pytest)

    assert r1 == r2
    assert calls["count"] == 1, "pytest_func deve ser chamado apenas 1x"
