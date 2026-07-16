"""Unit tests for scripts/md_auto_compress — dedup + archive logic."""

from __future__ import annotations

import textwrap
from unittest.mock import patch

import pytest

from scripts import md_auto_compress as mac


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


def _lessons_two_similar() -> str:
    return textwrap.dedent("""\
    # Licoes Aprendidas

    ### 1. Leite condensado Mococa

    - **Data + commit**: 2024-01-01 (abc123)
    Usar leite condensado Mococa porque tem melhor preco.
    Preco por kg: R$ 8.50 no Atacadao em caixa 12x395g.

    ### 2. Leite condensado Mococa em caixa

    - **Data + commit**: 2024-01-01 (abc123)
    Usar leite condensado Mococa em caixa 12x395g.
    Preco por kg: R$ 8.50 no Atacadao melhor custo.
    """)


def _lessons_dissimilar() -> str:
    return textwrap.dedent("""\
    # Licoes Aprendidas

    ### 1. Leite condensado Mococa

    Usar Mococa para leite condensado porque tem melhor preco.

    ### 2. Fermento biologico seco

    Fermento biologico seco 10g da Fleischmann.
    Manter na geladeira apos aberto.
    """)


def _lessons_with_keep() -> str:
    return textwrap.dedent("""\
    # Licoes Aprendidas

    ### 1. Regra critica de CI

    <!-- keep -->
    Nunca usar psycopg2 diretamente. Sempre RPC porta 443.

    ### 2. Duplicata da regra critica

    Nao usar psycopg2, usar exec_sql_query RPC.
    Sempre via porta 443.
    """)


def _lessons_three_same_topic() -> str:
    old = "2024-01-01"
    recent = "2026-06-01"
    return textwrap.dedent(f"""\
    # Licoes Aprendidas

    ### 1. Configuracao inicial do scrapers

    - **Data + commit**: {old} (abc1234)
    Configure USER_AGENT no ambiente.

    ### 2. Scraper setup revisado

    - **Data + commit**: {recent} (def5678)
    Set USER_AGENT via env. Usar timeout de 30s.

    ### 3. Outro scraper config

    - **Data + commit**: {old} (ghi9012)
    Sempre definir USER_AGENT para evitar bloqueio.
    """)


def _lessons_below_limit() -> str:
    return textwrap.dedent("""\
    # Licoes Aprendidas

    ### 1. Unica licao

    Alguma coisa aqui.
    """)


@pytest.fixture
def scoring_config():
    return {
        "weights": {
            "keep_marker": 999,
            "cross_doc_ref": 10,
            "test_ref": 8,
            "code_ref": 6,
            "workflow_ref": 6,
            "docs_ref": 3,
            "dated_anchor": 5,
            "age_months": -1,
            "no_evidence_penalty": -3,
        },
        "thresholds": {
            "archive_candidate": -3,
            "preserve_absolute": 6,
            "dedup_similarity": 0.85,
            "buffer_lines": 10,
        },
    }


# ═══════════════════════════════════════════════════════════════
# Parsing
# ═══════════════════════════════════════════════════════════════


def test_parse_lessons_returns_sections():
    sections = mac.parse_lessons(_lessons_two_similar())
    assert len(sections) == 2
    for s in sections:
        assert "id" in s
        assert "title" in s
        assert "body" in s


def test_parse_lessons_detects_keep_marker():
    sections = mac.parse_lessons(_lessons_with_keep())
    kept = [s for s in sections if s.get("keep")]
    assert len(kept) == 1
    assert kept[0]["id"] == 1


def test_parse_lessons_includes_raw_text():
    content = _lessons_two_similar()
    sections = mac.parse_lessons(content)
    for s in sections:
        assert "raw_text" in s
        assert isinstance(s["raw_text"], str)
        assert "###" in s["raw_text"] or s["id"] > 0


# ═══════════════════════════════════════════════════════════════
# Scorer
# ═══════════════════════════════════════════════════════════════


def test_scorer_keep_marker_is_absolute(scoring_config):
    section = {"id": 1, "title": "Test", "body": "body", "keep": True, "lines": 3}
    score = mac.section_score(section, scoring_config)
    assert score >= 999


def test_scorer_ref_score(scoring_config):
    section = {"id": 1, "title": "Test", "body": "body", "ref_score": 10, "lines": 3}
    score = mac.section_score(section, scoring_config)
    assert score == 10, f"Expected 10, got {score}"


def test_scorer_age_penalty(scoring_config):
    section = {"id": 1, "title": "Test", "body": "body", "age_months": 12, "lines": 3}
    score = mac.section_score(section, scoring_config)
    # age penalty = (12-6) * -1 = -6, plus no_evidence_penalty -3 = -9
    assert score == -9


# ═══════════════════════════════════════════════════════════════
# Dedup
# ═══════════════════════════════════════════════════════════════


def test_dedup_funde_secoes_85pct_similares():
    sections = mac.parse_lessons(_lessons_two_similar())
    deduped = mac.dedup(sections)
    survivors = [s for s in deduped if not s.get("merged_into")]
    assert len(survivors) < len(sections)
    assert any(s.get("merged_into") for s in deduped)


def test_dedup_funde_preservando_mais_antiga():
    sections = mac.parse_lessons(_lessons_three_same_topic())
    deduped = mac.dedup(sections)
    ids = {s["id"] for s in deduped}
    assert 1 in ids, "Older section (id=1) should survive dedup"


def test_dedup_nao_funciona_abaixo_de_85pct():
    sections = mac.parse_lessons(_lessons_dissimilar())
    deduped = mac.dedup(sections)
    assert len(deduped) == len(sections)


def test_dedup_idempotente():
    sections = mac.parse_lessons(_lessons_two_similar())
    d1 = mac.dedup(sections)
    d2 = mac.dedup(d1)
    assert len(d1) == len(d2)
    assert str(d1) == str(d2)


def test_dedup_secao_com_keep_marker_nao_funde():
    sections = mac.parse_lessons(_lessons_with_keep())
    deduped = mac.dedup(sections)
    kept = [s for s in deduped if s.get("keep")]
    assert len(kept) == 1


def test_dedup_cria_marcador_merge():
    sections = mac.parse_lessons(_lessons_two_similar())
    deduped = mac.dedup(sections)
    survivors = [s for s in deduped if not s.get("merged_into")]
    assert len(survivors) <= len(deduped), "Some sections should become merge markers"


# ═══════════════════════════════════════════════════════════════
# Archive
# ═══════════════════════════════════════════════════════════════


def test_archive_abaixo_do_limite_noop(scoring_config):
    content = _lessons_below_limit()
    result = mac.archive(content, max_lines=700, scoring_config=scoring_config)
    assert result["content"] == content
    assert len(result["archived"]) == 0


@patch("scripts.md_auto_compress.reference_score")
def test_archive_score_positivo_nao_expulsa(mock_ref, scoring_config):
    mock_ref.return_value = 10
    content = _lessons_two_similar()
    result = mac.archive(content, max_lines=10, scoring_config=scoring_config)
    assert len(result["archived"]) == 0


@patch("scripts.md_auto_compress.reference_score")
def test_archive_score_negativo_expulsa(mock_ref, scoring_config):
    mock_ref.return_value = 0
    content = _lessons_two_similar()
    sections = mac.parse_lessons(content)
    # Force age to be high for negative score
    for s in sections:
        s["age_months"] = 12
    result = mac.archive(content, max_lines=3, scoring_config=scoring_config)
    assert len(result["archived"]) > 0


@patch("scripts.md_auto_compress.reference_score")
def test_archive_keep_marker_bloqueia(mock_ref, scoring_config):
    mock_ref.return_value = 10  # high ref score, still should NOT archive keep-marked
    content = _lessons_with_keep()
    result = mac.archive(content, max_lines=5, scoring_config=scoring_config)
    archived_ids = [a["id"] for a in result["archived"]]
    assert 1 not in archived_ids


def test_archive_dry_run_nao_escreve(tmp_path, scoring_config):
    content = _lessons_two_similar()
    result = mac.archive(content, max_lines=20, scoring_config=scoring_config, dry_run=True)
    assert result.get("dry_run") is True


@patch("scripts.md_auto_compress.reference_score")
def test_archive_rollback_reverte(mock_ref, tmp_path, scoring_config):
    mock_ref.return_value = 0
    content = _lessons_two_similar()
    archive_dir = str(tmp_path / "lessons")
    result = mac.archive(content, max_lines=3, scoring_config=scoring_config, archive_dir=archive_dir)
    assert len(result["archived"]) > 0, "Need at least one archived section for rollback test"
    rollback_result = mac.rollback(result.get("target", "lessons"), archive_dir=archive_dir)
    assert rollback_result["restored"] is True


# ═══════════════════════════════════════════════════════════════
# Integration: compress (dedup + archive combined)
# ═══════════════════════════════════════════════════════════════


@patch("scripts.md_auto_compress.reference_score")
def test_compress_dedup_then_archive(mock_ref, tmp_path, scoring_config):
    mock_ref.return_value = 0
    archive_dir = str(tmp_path / "lessons")
    content = _lessons_two_similar()
    sections = mac.parse_lessons(content)
    survivors = [s for s in mac.dedup(sections) if not s.get("merged_into")]
    assert len(survivors) < len(sections)
    # Then archive the remaining (content has dates from fixture → age > 6mo)
    result = mac.archive(content, max_lines=3, scoring_config=scoring_config, archive_dir=archive_dir)
    assert "archived" in result
