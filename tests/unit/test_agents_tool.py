"""Unit tests for scripts/agents_tool — add_lesson cap, add_incident, promote_incident, validate_lessons.

Regression coverage for the LESSONS.md bottleneck work:
  - add_lesson() must block (BLOQUEADO) when the budget would be exceeded
  - max_lines_per_lesson is parsed from lessons_schema.yaml (not hardcoded 12)
  - validate_lessons() flags lessons over the per-lesson cap
  - add_incident()/promote_incident() write to monthly incidents shard + stub
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path

import pytest

from scripts import agents_tool as at


@pytest.fixture
def lessons_schema(tmp_path: Path) -> Path:
    schema = tmp_path / "config" / "lessons_schema.yaml"
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        textwrap.dedent("""\
            max_lines: 100
            max_lines_per_lesson: 4
            no_duplicates: true
            monotonic: true
            checkable: true
        """),
        encoding="utf-8",
    )
    return schema


# ═══════════════════════════════════════════════════════════════
# load_lessons_schema
# ═══════════════════════════════════════════════════════════════


def test_load_lessons_schema_parses_max_lines_per_lesson(tmp_path, monkeypatch):
    schema = tmp_path / "config" / "lessons_schema.yaml"
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text("max_lines: 775\nmax_lines_per_lesson: 25\n", encoding="utf-8")
    monkeypatch.setattr(at, "LESSONS_SCHEMA", schema)
    result = at.load_lessons_schema()
    assert result["max_lines"] == 775
    assert result["max_lines_per_lesson"] == 25


# ═══════════════════════════════════════════════════════════════
# validate_lessons
# ═══════════════════════════════════════════════════════════════


def test_validate_lessons_flags_lesson_over_max_lines(tmp_path, monkeypatch, lessons_schema):
    monkeypatch.setattr(at, "LESSONS_SCHEMA", lessons_schema)
    content = textwrap.dedent("""\
        # Lições

        ### 1. Primeira

        linha um
        linha dois

        ### 2. Segunda

        ok
    """)
    issues = at.validate_lessons(content)
    assert any("Lição #1 tem" in i and "max 4" in i for i in issues), issues


def test_validate_lessons_ok_under_max_lines(tmp_path, monkeypatch, lessons_schema):
    monkeypatch.setattr(at, "LESSONS_SCHEMA", lessons_schema)
    content = textwrap.dedent("""\
        # Lições

        ### 1. Primeira

        ok

        ### 2. Segunda

        ok
    """)
    issues = at.validate_lessons(content)
    assert not any("tem" in i for i in issues), issues


# ═══════════════════════════════════════════════════════════════
# add_lesson (budget cap)
# ═══════════════════════════════════════════════════════════════


def test_add_lesson_blocks_when_over_budget(tmp_path, monkeypatch):
    schema = tmp_path / "config" / "lessons_schema.yaml"
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text("max_lines: 4\n", encoding="utf-8")
    lessons = tmp_path / "LESSONS.md"
    lessons.write_text("# Lições\n\n### 1. Unica\n\ncorpo\n", encoding="utf-8")
    monkeypatch.setattr(at, "LESSONS", lessons)
    monkeypatch.setattr(at, "LESSONS_SCHEMA", schema)
    before = lessons.read_text(encoding="utf-8")
    result = at.add_lesson("Nova regra", "corpo da nova regra\ncom extra linha aqui")
    assert "BLOQUEADO" in result
    assert lessons.read_text(encoding="utf-8") == before


def test_add_lesson_appends_when_under_budget(tmp_path, monkeypatch, lessons_schema):
    lessons = tmp_path / "LESSONS.md"
    lessons.write_text("# Lições\n\n### 1. Unica\n\ncorpo\n", encoding="utf-8")
    monkeypatch.setattr(at, "LESSONS", lessons)
    monkeypatch.setattr(at, "LESSONS_SCHEMA", lessons_schema)
    result = at.add_lesson("Nova", "corpo curto")
    assert "adicionada" in result
    assert "### 2." in lessons.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# add_incident (monthly shard)
# ═══════════════════════════════════════════════════════════════


def test_add_incident_creates_and_appends_shard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    month = datetime.now().strftime("%Y-%m")
    first = at.add_incident("Flake CI", "- **Sintoma**: run X falhou")
    assert "Incidente #1" in first
    shard = tmp_path / "docs" / "incidents" / f"{month}.md"
    assert shard.exists()
    assert "### 1. Flake CI" in shard.read_text(encoding="utf-8")
    assert "**Data**" in shard.read_text(encoding="utf-8")

    second = at.add_incident("Outro", "- **Causa**: Y")
    assert "Incidente #2" in second
    assert "### 2. Outro" in shard.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# promote_incident (stub in LESSONS.md)
# ═══════════════════════════════════════════════════════════════


def test_promote_incident_adds_stub(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    month = datetime.now().strftime("%Y-%m")
    shard = tmp_path / "docs" / "incidents" / f"{month}.md"
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.write_text(
        f"# Incidentes — {month}\n\n\n### 1. Flake RPC\n\n- **Origem**: LESSONS.md #124\nSintoma: deploy engoliu erro\n",
        encoding="utf-8",
    )
    lessons = tmp_path / "LESSONS.md"
    lessons.write_text("# Lições\n", encoding="utf-8")
    monkeypatch.setattr(at, "LESSONS", lessons)

    result = at.promote_incident(month, 1)
    assert "promovida" in result.lower() or "promovido" in result.lower()
    lessons_text = lessons.read_text(encoding="utf-8")
    assert f"→ docs/incidents/{month}.md #1" in lessons_text


def test_promote_incident_missing_shard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = at.promote_incident("2020-01", 1)
    assert "nao encontrado" in result
