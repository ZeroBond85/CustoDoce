"""
Doc Utils — helpers compartilhados para sync_docs.py

Fornece funções puras e reutilizáveis para manipulação de markdown:
- Injeção/atualização de timestamp padronizado
- Extração de contadores citados (testes, páginas)
- Parsing AST de services/*.py
- Validação de formato Keep a Changelog
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, UTC
from pathlib import Path


# ── Timestamp ────────────────────────────────────────────────────

_TIMESTAMP_PAT = re.compile(
    r"> Última (atualização|revisão): \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC"
)


def get_timestamp() -> str:
    """Retorna timestamp ISO padronizado."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def inject_timestamp(content: str, label: str = "atualização") -> str:
    """Insere ou atualiza timestamp após o primeiro heading (# ...).

    Args:
        content: Conteúdo markdown.
        label: "atualização" (docs genéricos) ou "revisão" (ADRs, archive).

    Returns:
        Conteúdo com timestamp injetado/atualizado.
    """
    lines = content.splitlines()
    inserted = False

    for i, line in enumerate(lines):
        if line.startswith("# "):
            ts_line = f"> Última {label}: {get_timestamp()}"
            if i + 1 < len(lines) and _TIMESTAMP_PAT.match(lines[i + 1]):
                lines[i + 1] = ts_line
            else:
                lines.insert(i + 1, ts_line)
            inserted = True
            break

    if not inserted:
        lines.insert(0, f"> Última {label}: {get_timestamp()}")

    return "\n".join(lines) + "\n"


def file_has_timestamp(path: Path) -> tuple[bool, str]:
    """Verifica se arquivo tem timestamp padronizado.

    Returns:
        (has_ts, raw_timestamp_str or empty)
    """
    try:
        content = path.read_text(encoding="utf-8")
        m = _TIMESTAMP_PAT.search(content)
        if m:
            return True, m.group(0)
        return False, ""
    except Exception:
        return False, ""


# ── Contadores Citados ──────────────────────────────────────────

_COUNTER_PAT = re.compile(
    r"\b(\d{2,4})\s*(testes?|páginas?|telas?|módulos?|pages?|passing|total|collected)\b",
    re.IGNORECASE,
)


def extract_counters_cited(content: str) -> list[tuple[int, str]]:
    """Extrai números de contadores citados em um texto markdown.

    Returns:
        Lista de (valor, label) — ex: [(612, "passing"), (18, "páginas")]
    """
    matches = _COUNTER_PAT.findall(content)
    return [(int(num), label.lower()) for num, label in matches]


def check_counters_against_truth(
    cited: list[tuple[int, str]], truth: dict
) -> list[str]:
    """Compara contadores citados com a verdade do código.

    truth deve ter chaves como test_counts, pages_count.

    Returns:
        Lista de warnings (vazia se tudo ok).
    """
    warnings: list[str] = []
    for num, label in cited:
        if "test" in label or "passing" in label or "collected" in label:
            real_unit = truth.get("test_counts", {}).get("unit", 0)
            real_schema = truth.get("test_counts", {}).get("schema", 0)
            real_total = real_unit + real_schema
            if num not in (real_unit, real_schema, real_total):
                warnings.append(
                    f"  Contador testes: doc diz {num}, "
                    f"real unit={real_unit} schema={real_schema} total={real_total}"
                )
        elif "página" in label or "page" in label or "tela" in label or "módulo" in label:
            real_pages = truth.get("pages_count", 0)
            if num != real_pages:
                warnings.append(
                    f"  Contador páginas: doc diz {num}, real={real_pages}"
                )
    return warnings


# ── AST Parsing ──────────────────────────────────────────────────


def parse_services_ast(services_dir: Path) -> dict[str, dict[str, dict]]:
    """Extrai funções públicas de services/*.py via AST.

    Returns:
        {module_name: {func_name: {"signature": str, "docstring": str}}}
    """
    api: dict[str, dict[str, dict]] = {}
    for py_file in sorted(services_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        funcs: dict[str, dict] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                doc = ast.get_docstring(node) or ""
                # Build a simple signature string
                args = []
                for arg in node.args.args:
                    annotation = ""
                    if arg.annotation:
                        try:
                            annotation = f": {ast.unparse(arg.annotation)}"
                        except Exception:
                            annotation = ""
                    args.append(f"{arg.arg}{annotation}")
                sig = f"{node.name}({', '.join(args)})"
                funcs[node.name] = {"signature": sig, "docstring": doc}

        if funcs:
            api[py_file.stem] = funcs
    return api


def generate_api_md(module_name: str, funcs: dict[str, dict]) -> str:
    """Gera markdown para um módulo de serviço.

    Args:
        module_name: Nome do módulo (ex: price_service).
        funcs: {func_name: {"signature": str, "docstring": str}}

    Returns:
        Conteúdo markdown.
    """
    lines = [
        f"# `{module_name}` — API",
        "",
        f"> Última atualização: {get_timestamp()}",
        f"> Gerado por AST parsing dos serviços em `services/{module_name}.py`.",
        "",
        f"## Funções Públicas ({len(funcs)})",
        "",
    ]

    for fname in sorted(funcs.keys()):
        info = funcs[fname]
        lines.append(f"### {info['signature']}")
        if info["docstring"]:
            # Use first paragraph as summary
            para = info["docstring"].strip().split("\n\n")[0]
            lines.append("")
            lines.append(para)
        lines.append("")

    return "\n".join(lines) + "\n"


# ── Changelog Validation ────────────────────────────────────────


_CHANGELOG_ENTRY_PAT = re.compile(r"^## \[\d+\.\d+\.\d+\]")


def validate_changelog(content: str) -> list[str]:
    """Valida formato Keep a Changelog.

    Returns:
        Lista de warnings (vazia se tudo ok).
    """
    warnings: list[str] = []
    lines = content.splitlines()
    found_version = False
    prev_version: str | None = None

    for i, line in enumerate(lines):
        m = _CHANGELOG_ENTRY_PAT.match(line)
        if m:
            version = m.group(0).strip()
            if prev_version and version >= prev_version:
                warnings.append(
                    f"  Linha {i + 1}: versão {version} não é anterior a {prev_version}"
                    " (deve ser reverse chronological)"
                )
            prev_version = version
            found_version = True

    if not found_version:
        warnings.append("  Nenhuma entrada de versão encontrada (## [X.Y.Z])")

    return warnings


# ── Frontmatter I/O (v2 sync — aditivo, convive com sync_docs) ──
#
# Contrato mínimo: frontmatter YAML no topo do .md delimita estado
# versionado. sync_docs.py (legacy) continua intocado; sync_md_v2.py
# consome este módulo para pulse/snapshot/diff/apply.


_FRONTMATTER_PAT = re.compile(
    r"\A---\s*\n(?P<fm>.*?\n)---\s*\n(?P<body>.*)\Z",
    re.DOTALL,
)


def read_frontmatter(path: Path) -> tuple[dict, str]:
    """Lê YAML frontmatter + corpo de um .md.

    Returns:
        (frontmatter_dict, body_str). Se ausente, retorna ({}, content).
        Tolerante: erro de YAML → ({}, content).
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}, ""

    m = _FRONTMATTER_PAT.match(content)
    if not m:
        return {}, content

    try:
        import yaml

        fm = yaml.safe_load(m.group("fm")) or {}
        if not isinstance(fm, dict):
            return {}, content
    except Exception:
        return {}, content

    return fm, m.group("body")


def write_frontmatter(path: Path, fm: dict, body: str) -> None:
    """Escreve arquivo com frontmatter YAML + corpo.

    Idempotente: ordem das chaves preservada pela dict.
    """
    import yaml

    fm_block = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    body = body.lstrip("\n")
    content = f"---\n{fm_block}---\n{body}"
    path.write_text(content, encoding="utf-8")


def pulse_check(fm: dict, truth: dict) -> list[str]:
    """Compara truth_at (no frontmatter) com truth atual do projeto.

    Args:
        fm: frontmatter com chave 'truth_at' opcional
            {tests_total, pages_count, nota, risk, ...}.
        truth: estado real
            {test_counts: {unit, schema, ...}, pages_count, ...}.

    Returns:
        Lista de warnings. Vazia se coerente.
    """
    warnings: list[str] = []
    truth_at = fm.get("truth_at") or {}
    if not isinstance(truth_at, dict) or not truth_at:
        return warnings

    real_unit = truth.get("test_counts", {}).get("unit", 0)
    real_schema = truth.get("test_counts", {}).get("schema", 0)
    real_total = real_unit + real_schema
    real_pages = truth.get("pages_count", 0)

    if "tests_total" in truth_at and truth_at["tests_total"] != real_total:
        warnings.append(
            f"truth_at.tests_total desatualizado: "
            f"doc={truth_at['tests_total']} real={real_total}"
        )
    if "pages_count" in truth_at and truth_at["pages_count"] != real_pages:
        warnings.append(
            f"truth_at.pages_count desatualizado: "
            f"doc={truth_at['pages_count']} real={real_pages}"
        )

    return warnings
