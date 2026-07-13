import textwrap

from scripts import agents_tool


def _clean_lessons() -> str:
    return textwrap.dedent("""\
    # Lições Aprendidas

    ### 1. Primeira licao

    - **Data**: 2026-01-01
    - **Sintoma**: algo
    - **Causa**: algo
    - **Correcao**: algo

    ### 2. Segunda licao

    - **Data**: 2026-01-02
    """)


def _duplicate_lessons() -> str:
    return textwrap.dedent("""\
    # Lições Aprendidas

    ### 1. Primeira licao
    body

    ### 1. Outra com mesmo numero
    body
    """)


def _wrong_heading_lessons() -> str:
    return textwrap.dedent("""\
    # Lições Aprendidas

    ### 1. Primeira licao
    body

    ## 2. Segunda com heading errado
    body
    """)


def _non_monotonic_lessons() -> str:
    return textwrap.dedent("""\
    # Lições Aprendidas

    ### 1. Primeira licao
    body

    ### 3. Terceira (pula 2)
    body

    ### 2. Segunda (volta)
    body
    """)


def _regras_correct() -> str:
    return textwrap.dedent("""\
    # REGRAS.md

    ## Pre-commit Hook

    1. SECRET GUARD
    1.5 GITIGNORE IMPORTS
    1.7 DETECT-SECRETS
    1.8 RUFF LINT
    2. DOC SYNC
    3. SIZE GUARD
    4. DOC WATCHDOG
    5. AGENTS SCHEMA
    6. SKILL DRIFT
    7. RESIDUE GUARD
    8. CRLF GUARD
    """)


def _regras_wrong_count() -> str:
    return textwrap.dedent("""\
    # REGRAS.md

    ## Pre-commit Hook

    1. SECRET GUARD
    2. DOC SYNC
    """)


class TestValidateLessons:
    """Test agents_tool.validate_lessons() against various LESSONS.md states."""

    def test_valid_passes(self):
        issues = agents_tool.validate_lessons(content=_clean_lessons())
        assert issues == [], f"Expected no issues, got: {issues}"

    def test_duplicate_number_detected(self):
        issues = agents_tool.validate_lessons(content=_duplicate_lessons())
        assert any("duplicada" in i for i in issues), f"Expected duplicate issue, got: {issues}"

    def test_wrong_heading_format_detected(self):
        issues = agents_tool.validate_lessons(content=_wrong_heading_lessons())
        assert any(
            "usa '## '" in i for i in issues
        ), f"Expected heading format issue, got: {issues}"

    def test_non_monotonic_detected(self, capsys):
        issues = agents_tool.validate_lessons(content=_non_monotonic_lessons())
        stderr = capsys.readouterr().err
        assert "Ordem monot" in stderr, f"Expected monotonic warning in stderr, got: {stderr}"
        assert issues == [], "Monotonic should be warning, not blocking issue"


class TestValidateRegras:
    """Test agents_tool.validate_regras() against various REGRAS.md states."""

    def test_correct_layers_passes(self):
        issues = agents_tool.validate_regras(content=_regras_correct())
        assert issues == [], f"Expected no issues, got: {issues}"

    def test_wrong_layer_count_detected(self):
        issues = agents_tool.validate_regras(content=_regras_wrong_count())
        assert any(
            "documenta" in i and "espera" in i for i in issues
        ), f"Expected layer count issue, got: {issues}"

    def test_missing_section_reported(self):
        content = "# REGRAS.md\n\nSome content\n"
        issues = agents_tool.validate_regras(content=content)
        assert any(
            "nao encontrada" in i for i in issues
        ), f"Expected missing section issue, got: {issues}"
