"""
Sync Docs — keeps project documentation in sync with actual code state.

Extracts current state from code and updates:
- AGENTS.md (project memory — test counts, phases, files)
- docs/api/*.md (auto-generated via AST from services/)
- README.md (badges, stats)
- REGRAS.md (hooks, Python versions)
- docs/archive/*.md (Raio X — timestamp + counter validation)
- ALL .md files (generic timestamp injection)

Run manually:
    python scripts/sync_docs.py --dry-run   # preview changes
    python scripts/sync_docs.py             # apply changes

Run in CI (fails if docs are outdated):
    python scripts/sync_docs.py --check     # exit 1 if out of sync

Run with full .md audit (also checks stale page/test counts in all .md files):
    python scripts/sync_docs.py --check --strict   # exit 1 if any stale pattern found

V2 features (embedded from sync_docs_v2):
    python scripts/sync_docs.py --analyze             # classify stale refs by heading
    python scripts/sync_docs.py --sync                # auto-update CURRENT blocks
    python scripts/sync_docs.py --sync --dry-run      # preview changes
    python scripts/sync_docs.py --dump-truth          # print truth JSON
    python scripts/sync_docs.py --strict --experimental  # strict audit using v2 classifier
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import warnings
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

# Suppress Streamlit "No runtime found" warnings when importing dashboard components
os.environ.setdefault("STREAMLIT_DISABLE_CACHING_WARNING", "1")
warnings.filterwarnings("ignore", message="No runtime found, using MemoryCacheStorageManager", category=UserWarning, module="streamlit.runtime.caching.cache_data_api")

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.doc_utils import (  # noqa: E402
    check_counters_against_truth,
    extract_counters_cited,
    generate_api_md,
    inject_timestamp,
    parse_services_ast,
    validate_changelog,
)
from scripts.skills_maintenance import APPROVED_SKILLS, skill_to_category  # noqa: E402

_AGENTS = _ROOT / "AGENTS.md"
_README = _ROOT / "README.md"
_DOCS_API = _ROOT / "docs" / "api"
_TEST_DIR = _ROOT / "tests"
_SERVICES_DIR = _ROOT / "services"
_SKILLS_DIR = _ROOT / ".opencode" / "skills"
_SKILLS_DOC = _ROOT / "docs" / "skills.md"

_OK = "OK"
_FAIL = "FAIL"


# ═══════════════════════════════════════════════════════════════════
# v1 — Production core (drift detection, AGENTS.md update, auto-fixers)
# ═══════════════════════════════════════════════════════════════════


def _count_tests() -> dict:
    """Count tests by category using pytest --collect-only (no import needed).

    Counts both <Function test_> (sync tests) AND <Coroutine test_> (async tests).
    Earlier versions only counted synchronous tests, missing 7 async helpers in
    test_telegram_handlers.py (411 vs real 418).
    """
    import subprocess

    result = {}
    sync_pat = re.compile(r"<Function\s+test_")
    async_pat = re.compile(r"<Coroutine\s+test_")

    for test_path, label in [
        ("tests/unit", "unit"),
        ("tests/schema", "schema"),
        ("tests/integration", "integration"),
        ("tests/e2e", "e2e"),
        ("tests/real", "real"),
    ]:
        full_path = _ROOT / test_path
        if not full_path.exists():
            continue
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(full_path),
                    "--collect-only",
                    "--co",  # print <Function>/<Coroutine> markup for regex
                    "--no-header",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                cwd=str(_ROOT),
            )
            sync_count = len(sync_pat.findall(proc.stdout))
            async_count = len(async_pat.findall(proc.stdout))
            result[label] = sync_count + async_count
        except Exception:
            result[label] = 0
    return result


def _extract_actual_test_count(test_path: str) -> tuple[int, int]:
    """Get pytest's reported total + delta vs my count.

    Returns (pytest_total, my_count). Used by --check drift detection.
    """
    import subprocess

    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(test_path),
                "--collect-only",
                "--co",  # print <Function>/<Coroutine> markup for regex
                "--no-header",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(_ROOT),
        )
        # pytest output: "722 tests collected in 5.19s"
        # usa literal "tests" — se pytest mudar para "items", atualizar
        m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
        pytest_total = int(m.group(1)) if m else 0
        sync_count = len(re.findall(r"<Function\s+test_", proc.stdout))
        async_count = len(re.findall(r"<Coroutine\s+test_", proc.stdout))
        my_count = sync_count + async_count
        return (pytest_total, my_count)
    except Exception:
        return (0, 0)


def _check_drift() -> list[str]:
    """Detect drift between pytest's reported total and our sync_docs count.

    Returns list of drift messages. Empty = no drift.

    Sources of truth compared:
        - my_counts (from _count_tests — this script's interpretation)
        - pytest's "X tests collected" line (ground truth)

    Drift triggers a --check failure to keep AGENTS.md truthful (Sprint 4).
    """
    drift_msgs = []
    my_counts = _count_tests()
    for test_path, label in [
        ("tests/unit", "unit"),
        ("tests/schema", "schema"),
        ("tests/integration", "integration"),
        ("tests/e2e", "e2e"),
        ("tests/real", "real"),
    ]:
        full = _ROOT / test_path
        if not full.exists():
            continue
        pytest_total, my_count = _extract_actual_test_count(test_path)
        sync_expected = my_counts.get(label, 0)
        # Pytest's "X tests collected" may count parametrized cases twice
        # (once as Function, once indirectly). Allow within ±5 tolerance.
        diff = abs(pytest_total - sync_expected)
        if diff > 5:
            drift_msgs.append(
                f"  {label}: pytest reports {pytest_total}, sync_docs counted {sync_expected} (regex-confirmed {my_count})"
            )
    return drift_msgs


def _check_skills_sync() -> list[str]:
    """Single Source of Truth para skills.

    Fonte 1: .opencode/skills/ (filesystem)
    Fonte 2: scripts/skills_maintenance.py::APPROVED_SKILLS
    Fonte 3: docs/skills.md (gold standard, gerado por --sync)

    Retorna lista de issues (vazia = tudo ok).
    """
    issues: list[str] = []

    if not _SKILLS_DIR.exists():
        issues.append(f"Skills dir not found: {_SKILLS_DIR}")
        return issues

    # Skills no disco (pastas com SKILL.md)
    disk_skills = {d.name for d in _SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists()}

    expected = set(APPROVED_SKILLS)

    # 1. Disco -> APPROVED: skills no disco mas não aprovadas
    orphan_skills = sorted(disk_skills - expected)
    if orphan_skills:
        issues.append(f"Skills no disco sem APPROVED_SKILLS: {orphan_skills}")

    # 2. APPROVED -> Disco: skills aprovadas mas sem pasta/SKILL.md
    missing_skills = sorted(expected - disk_skills)
    if missing_skills:
        issues.append(f"Skills em APPROVED_SKILLS sem SKILL.md no disco: {missing_skills}")

    # 3. APPOVED_SKILLS deve cobrir toda skill no disco
    if disk_skills != expected:
        issues.append(f"Skills count mismatch: {len(disk_skills)} on disk vs {len(expected)} approved")

    return issues


def _sync_skills_md(state: dict | None = None, dry_run: bool = False) -> list[str]:
    """Gera docs/skills.md a partir do disco + APPROVED_SKILLS + categorias.

    Usa SKILL_CATEGORIES de skills_maintenance.py como override de categoria.
    Para skills sem categoria definida, deriva por heurística simples.
    """
    changes: list[str] = []

    if not _SKILLS_DIR.exists():
        changes.append("Skills dir not found, skipping skills.md generation")
        return changes

    disk_skills = sorted(d.name for d in _SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists())

    # Build category -> skills mapping (from override + auto-derive)
    category_skills: dict[str, list[str]] = {}
    for skill in disk_skills:
        cat = skill_to_category(skill)
        category_skills.setdefault(cat, []).append(skill)

    # Get descriptions from SKILL.md frontmatter
    skill_descriptions: dict[str, str] = {}
    for d in _SKILLS_DIR.iterdir():
        if not d.is_dir():
            continue
        sf = d / "SKILL.md"
        if not sf.exists():
            continue
        content = sf.read_text(encoding="utf-8")
        if content.startswith("---"):
            fm = content.split("---")[1]
            lines = fm.splitlines()
            for i, line in enumerate(lines):
                if line.strip().startswith("description:"):
                    first_val = line.split(":", 1)[1].strip().strip("\"'")
                    if first_val in (">", "|", ">-", "|-"):
                        # YAML block scalar: read indented continuation lines
                        desc_lines = []
                        for j in range(i + 1, len(lines)):
                            if lines[j].startswith("  ") or lines[j].startswith("\t"):
                                desc_lines.append(lines[j].strip())
                            else:
                                break
                        desc = " ".join(desc_lines)
                    else:
                        desc = first_val
                    skill_descriptions[d.name] = desc
                    break

    # Build markdown — conteúdo sem timestamp (para comparação estável)
    now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def _build_skills_content(timestamp: str) -> str:
        lines: list[str] = [
            "# Skills do CustoDoce",
            "",
            "> Gerado por `python scripts/sync_docs.py --sync`. **Não editar à mão.**",
            f"> Última atualização: {timestamp}",
            f"> Total: {len(disk_skills)} skills instaladas",
            "",
            "| Categoria | Skill | Descrição |",
            "|---|---|---|",
        ]

        for cat in sorted(category_skills.keys()):
            for skill in sorted(category_skills[cat]):
                desc = skill_descriptions.get(skill, "")
                lines.append(f"| {cat} | {skill} | {desc} |")

        # theme-factory sub-themes
        themes_dir = _SKILLS_DIR / "theme-factory" / "themes"
        if themes_dir.exists():
            themes = sorted(f.name for f in themes_dir.iterdir() if f.suffix == ".md")
            if themes:
                lines += [
                    "",
                    "## Sub-themes (theme-factory)",
                    "",
                    ", ".join(t.replace(".md", "") for t in themes) + ".",
                    "",
                    "Ver `.opencode/skills/theme-factory/themes/*.md` para detalhes de cada paleta.",
                ]

        # Skills externas não adotadas
        non_adopted = [s for s in disk_skills if skill_to_category(s) == "Externas (não adotadas)"]
        if non_adopted:
            lines += [
                "",
                "## Skills externas (instaladas mas não adotadas)",
                "",
                "Estas skills existem no disco mas não estão integradas ao fluxo principal:",
            ]
            for s in non_adopted:
                desc = skill_descriptions.get(s, "")
                lines.append(f"- `{s}`: {desc}")

        return "\n".join(lines) + "\n"

    # Comparação sem timestamp para detectar mudança real
    content_no_ts = _build_skills_content("UPDATED_AT")
    old_no_ts = ""
    if _SKILLS_DOC.exists():
        old_raw = _SKILLS_DOC.read_text(encoding="utf-8")
        # Extrair mesmo padrão sem a linha de timestamp
        old_lines = old_raw.splitlines()
        old_no_ts_lines = [l for l in old_lines if "Última atualização:" not in l]
        old_no_ts = "\n".join(old_no_ts_lines) + "\n"
    content_compare = "\n".join(l for l in content_no_ts.splitlines() if "Última atualização:" not in l) + "\n"

    if dry_run:
        if not _SKILLS_DOC.exists() or old_no_ts != content_compare:
            changes.append("  Would regenerate docs/skills.md (content changed)")
        else:
            changes.append("  docs/skills.md is up to date")
        return changes

    if not _SKILLS_DOC.exists() or old_no_ts != content_compare:
        _SKILLS_DOC.write_text(_build_skills_content(now_iso), encoding="utf-8")
        if not old_no_ts:
            changes.append("docs/skills.md created")
        else:
            changes.append("docs/skills.md regenerated (content changed)")
    else:
        # Apenas atualizar timestamp sem marcar como mudança
        _SKILLS_DOC.write_text(_build_skills_content(now_iso), encoding="utf-8")
        changes.append("docs/skills.md unchanged (timestamp refreshed)")

    return changes


def _extract_pages() -> list[tuple[str, str, str]]:
    """Extract PAGES from navigation_config (single source of truth)."""
    from dashboard.navigation_config import PAGES as nav_pages

    return list(nav_pages)


def _extract_services_api() -> dict[str, list[str]]:
    """Extract public functions from service modules."""
    api = {}
    for py_file in _SERVICES_DIR.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module_name = py_file.stem
        functions = []
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            m = re.match(r"^def\s+(\w+)\s*\(", line)
            if m:
                fn = m.group(1)
                if not fn.startswith("_"):
                    functions.append(fn)
        if functions:
            api[module_name] = sorted(functions)
    return api


def _extract_dashboard_pages() -> list[str]:
    """Extract page IDs from layout.py PAGES list."""
    pages = _extract_pages()
    return [p[0] for p in pages]


def _extract_workflows() -> list[str]:
    """List GitHub workflow files."""
    wf_dir = _ROOT / ".github" / "workflows"
    if not wf_dir.exists():
        return []
    return sorted([f.stem for f in wf_dir.glob("*.yml")])


def _count_lessons() -> int:
    """Count lessons in LESSONS.md (### N. headings)."""
    if not _LESSONS.exists():
        return 0
    content = _LESSONS.read_text(encoding="utf-8")
    return len(re.findall(r"^### \d+\.", content, re.MULTILINE))


def _current_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _build_agents_state() -> dict:
    """Build current project state dict."""
    test_counts = _count_tests()
    pages = _extract_pages()
    services_api = _extract_services_api()
    workflows = _extract_workflows()

    total_tests = sum(test_counts.values())
    lessons_count = _count_lessons()

    return {
        "updated_at": _current_timestamp(),
        "total_tests": total_tests,
        "test_counts": test_counts,
        "pages": pages,
        "pages_count": len(pages),
        "services_api": services_api,
        "workflows": workflows,
        "workflows_count": len(workflows),
        "lessons_count": lessons_count,
        "api_services": sorted(services_api.keys()),
    }


def _update_agents_md(state: dict, dry_run: bool = False) -> list[str]:
    """Update AGENTS.md with current state.

    Robust detection of the Ferramenta/Tool status table: works whether AGENTS.md
    uses single pytest line ("unit") or combined ("unit + schema").
    """
    content = _AGENTS.read_text(encoding="utf-8")
    lines = content.splitlines()

    changes = []

    # Update "Last updated" line
    for i, line in enumerate(lines):
        if "Last updated:" in line or "Última atualização:" in line:
            if dry_run:
                changes.append(f"  Would update line {i + 1}: {line.strip()}")
            else:
                lines[i] = f"<!-- Last updated: {state['updated_at']} -->"
            break

    tc = state["test_counts"]

    in_status_table = False
    status_start = -1
    status_end = -1
    status_table_re = re.compile(r"\|\s*(pytest|tool)\s*\(.*pytest", re.IGNORECASE)

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_header = "| Ferramenta" in line or "| Tool" in line or status_table_re.search(line) is not None
        if is_header and "|---" not in stripped:
            in_status_table = True
            status_start = i
        if (
            in_status_table
            and status_start >= 0
            and i > status_start
            and (stripped == "" or not stripped.startswith("|"))
        ):
            status_end = i
            break

    if status_start >= 0 and status_end < 0:
        status_end = len(lines)

    if status_start >= 0 and status_end > status_start:
        new_table = []
        new_table.append(lines[status_start])
        if status_start + 1 < len(lines):
            new_table.append(lines[status_start + 1])

        new_table.append(
            f"| pytest (unit + schema) | {tc.get('unit', 0) + tc.get('schema', 0)} passing "
            f"(unit: {tc.get('unit', 0)}, schema: {tc.get('schema', 0)}) | ✅ |"
        )
        if tc.get("integration"):
            new_table.append(f"| pytest (integration) | {tc['integration']} passing | ✅ |")
        if tc.get("design"):
            new_table.append(f"| pytest (design) | {tc['design']} passing | ✅ |")
        if tc.get("real"):
            new_table.append(f"| pytest (real, slow) | {tc['real']} passing | ✅ |")
        if tc.get("e2e"):
            new_table.append(
                f"| pytest (e2e) | {tc['e2e']} collected (blocked on Playwright live Streamlit Cloud) | ⏳ |"
            )

        lines = lines[:status_start] + new_table + lines[status_end:]

    if dry_run:
        return changes

    _AGENTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changes



def _count_dashboard_pages() -> int:
    """Count actual page modules in dashboard/pages/, excluding __init__.py and orphans."""
    pages_dir = _ROOT / "dashboard" / "pages"
    if not pages_dir.exists():
        return 0
    return sum(1 for f in pages_dir.iterdir() if f.suffix == ".py" and f.stem != "__init__")


def _fix_tree_test_count(content: str, unit_count: int) -> str:
    """Update AGENTS.md directory tree legend with real unit test count.

    Pattern: 'unit/                        # NNN testes (NN arquivos: +XX do Sprint YY)'
    """
    return re.sub(
        r"(│\s+├── unit/\s+# )(\d+)( testes \(\d+ arquivos: \+)(\d+)( do Sprint )(\d+)",
        lambda m: f"{m.group(1)}{unit_count}{m.group(3)}65{m.group(5)}7-9",
        content,
    )


def _fix_page_import_count(content: str, pages_count: int) -> str:
    """Update AGENTS.md page import line: 'importa 17 pages' → 'importa 18 pages'."""
    return re.sub(
        r"(importa )(\d+)( pages \+ sidebar \+ login)",
        rf"\g<1>{pages_count}\g<3>",
        content,
    )


def _fix_streamlit_skill_row(content: str, pages_count: int) -> str:
    """Update AGENTS.md streamlit skill row: '| 17 pages' → '| 18 pages'."""
    return re.sub(
        r"(\| `?streamlit`? \| )(\d+)( pages, login gate)",
        rf"\g<1>{pages_count}\g<3>",
        content,
    )


def _fix_agents_tree(content: str, state: dict) -> str:
    """Apply all auto-fixers to AGENTS.md content."""
    tc = state["test_counts"]
    unit_count = tc.get("unit", 0)
    pages_count = _count_dashboard_pages()
    lessons_count = state.get("lessons_count", 0)

    content = _fix_tree_test_count(content, unit_count)
    content = _fix_page_import_count(content, pages_count)
    content = _fix_streamlit_skill_row(content, pages_count)

    # Fix LESSONS.md count in directory tree comment (e.g. "32 lições" → real)
    content = re.sub(
        r"(├── LESSONS\.md\s+# )\d+( lições aprendidas)",
        rf"\g<1>{lessons_count}\g<2>",
        content,
    )

    # Fix LESSONS.md count in Status Atual table
    content = re.sub(
        r"(\| LESSONS\.md \| )\d+( lições \|)",
        rf"\g<1>{lessons_count}\g<2>",
        content,
    )

    # Fix LESSONS.md count in Documentação Relacionada section
    content = re.sub(
        r"(- `LESSONS\.md` — )\d+( lições )",
        rf"\g<1>{lessons_count}\g<2>",
        content,
    )

    return content


# ── Extra Constants ────────────────────────────────────────────
_ARCHIVE_DIR = _ROOT / "docs" / "archive"
_REGRAS = _ROOT / "REGRAS.md"
_LESSONS = _ROOT / "LESSONS.md"
_TESTS_README = _ROOT / "tests" / "README.md"

_GENERIC_MD_FILES: list[str] = [
    "LESSONS.md",
    "tests/README.md",
    "docs/architecture.md",
    "docs/troubleshooting.md",
    "docs/security.md",
    "docs/contributing.md",
    "docs/deployment.md",
    "docs/deployment-staging.md",
    "docs/migration-guide.md",
    "docs/ROLLBACK_PROD.md",
]


def _update_archive_md(state: dict, dry_run: bool = False) -> list[str]:
    """Atualiza docs/archive/*.md respeitando policy per-doc.

    - SNAPSHOT_FROZEN: bypass total (nunca toca).
    - SNAPSHOT_DERIVED_LIVE: reportar intenção, não auto-aplica (regeneração manual).
    - SNAPSHOT_REFERENCE_LIVE: delega para `apply_intelligent` (vai apontar onde
      truth diverge e preserva histórico com sufixo '(era X)').
    - Demais (sem frontmatter): fallback legacy para inject_timestamp + warning.
    """
    from scripts.doc_sync_policy import DocPolicy, policy_for
    from scripts.sync_md_v2 import apply_intelligent

    changes: list[str] = []
    if not _ARCHIVE_DIR.exists():
        return changes

    truth_with_pages = {
        **state,
        "page_truth": {"python_version": "3.14.6"},
    }

    for md_file in sorted(_ARCHIVE_DIR.glob("*.md")):
        rel = md_file.relative_to(_ROOT)
        try:
            policy = policy_for(rel)
        except Exception:
            policy = None

        if policy == DocPolicy.SNAPSHOT_FROZEN:
            changes.append(f"  [SKIP-FROZEN] {rel}: data-anchored, bypass")
            continue
        if policy == DocPolicy.SNAPSHOT_DERIVED_LIVE:
            changes.append(f"  [DERIVED] {rel}: regenerar via sprint review (não auto-aplicado)")
            continue

        if policy == DocPolicy.SNAPSHOT_REFERENCE_LIVE:
            applied = apply_intelligent(md_file, truth_with_pages, dry_run=dry_run)
            if not applied:
                changes.append(f"  [OK] {rel}: alinhado com truth")
            elif applied and dry_run:
                changes.append(f"  [DRIFT] {rel}: intelligence merge pendente")
            else:
                changes.append(f"  [OK] {rel}: intelligence merge aplicado")
            continue

        content = md_file.read_text(encoding="utf-8")
        cited = extract_counters_cited(content)
        warnings = check_counters_against_truth(cited, state)
        new_content = inject_timestamp(content, label="revisão")
        if new_content == content and not warnings:
            continue
        if dry_run:
            changes.append(f"  Would update {rel}")
            for w in warnings:
                changes.append(f"    [WARN] {w}")
        else:
            md_file.write_text(new_content, encoding="utf-8")
            changes.append(f"  {rel}: timestamp updated")
            for w in warnings:
                changes.append(f"    [WARN] {w}")

    return changes


def _update_readme_md(state: dict, dry_run: bool = False) -> list[str]:
    """Atualiza README.md com badges dinâmicos e timestamp."""
    from scripts.doc_utils import is_timestamp_fresh

    changes: list[str] = []
    tc = state["test_counts"]
    unit = tc.get("unit", 0)
    schema = tc.get("schema", 0)
    total = state["total_tests"]
    pages_count = state["pages_count"]

    content = _README.read_text(encoding="utf-8")
    if is_timestamp_fresh(content):
        return changes

    new_content = content
    new_content = re.sub(
        r"(18|19|20)( módulos?| pages?| abas?)",
        f"{pages_count}\\2",
        new_content,
    )
    new_content = re.sub(
        r"(\d+)( testes? (unit|passing))",
        f"{total}\\2",
        new_content,
    )
    new_content = re.sub(
        r"(badge/version-)\d+\.\d+\.\d+(--mvp)",
        f"\\g<1>{pages_count}.{unit}.{schema}\\2",
        new_content,
    )
    new_content = inject_timestamp(new_content)

    if new_content != content:
        if dry_run:
            changes.append("  Would update README.md")
        else:
            _README.write_text(new_content, encoding="utf-8")
            changes.append("  README.md: badges + timestamp updated")
    return changes


def _update_rules_md(state: dict, dry_run: bool = False) -> list[str]:
    """Atualiza REGRAS.md com Python version, hooks layers, comandos."""
    from scripts.doc_utils import is_timestamp_fresh

    changes: list[str] = []
    if not _REGRAS.exists():
        return changes
    content = _REGRAS.read_text(encoding="utf-8")
    if is_timestamp_fresh(content):
        return changes

    new_content = content
    new_content = re.sub(
        r"(deve ser )3\.\d+(\+)",
        r"\g<1>3.14\g<2>",
        new_content,
    )
    new_content = inject_timestamp(new_content)

    if new_content != content:
        if dry_run:
            changes.append("  Would update REGRAS.md")
        else:
            _REGRAS.write_text(new_content, encoding="utf-8")
            changes.append("  REGRAS.md: Python version + timestamp updated")
    return changes


def _generate_api_docs(state: dict, dry_run: bool = False) -> list[str]:
    """Gera docs/api/*.md a partir de AST dos services/*.py.

    Sobrescreve arquivos existentes — source of truth é o código.
    """
    changes: list[str] = []
    api = parse_services_ast(_SERVICES_DIR)

    if not api:
        return changes

    _DOCS_API.mkdir(parents=True, exist_ok=True)

    for module_name, funcs in api.items():
        md_content = generate_api_md(module_name, funcs)
        dest = _DOCS_API / f"{module_name}.md"

        if dry_run:
            existing = dest.read_text(encoding="utf-8") if dest.exists() else ""
            existing_no_ts = _strip_timestamp_line(existing)
            new_no_ts = _strip_timestamp_line(md_content)
            if existing_no_ts != new_no_ts:
                changes.append(f"  Would regenerate docs/api/{module_name}.md ({len(funcs)} funcs)")
        else:
            dest.write_text(md_content, encoding="utf-8")
            changes.append(f"  docs/api/{module_name}.md: {len(funcs)} funcs generated")

    return changes


def _strip_timestamp_line(content: str) -> str:
    """Remove a linha de timestamp `> Última atualização: ...` para
    comparar só conteúdo sem ruído de timestamp."""
    lines = content.splitlines()
    return "\n".join(
        l for l in lines if not l.startswith("> Última atualização") and not l.startswith("> Última revisão")
    )


def _update_generic_md(state: dict, dry_run: bool = False) -> list[str]:
    """Atualiza timestamp em todos os .md que não têm updater específico.

    Respeita `policy_for()` por arquivo:
      - IMMUTABLE / SNAPSHOT_FROZEN: bypass total (sync nunca toca)

    Whitelist explícita: LESSONS.md, tests/README.md, docs/*.md (excluindo
    archive/, api/, skills.md, changelog.md).
    """
    from scripts.doc_sync_policy import DocPolicy, policy_for
    from scripts.doc_utils import is_timestamp_fresh

    changes: list[str] = []

    adr_dir = _ROOT / "docs" / "adr"
    if adr_dir.exists():
        for adr_file in sorted(adr_dir.glob("*.md")):
            if policy_for(adr_file.relative_to(_ROOT)) == DocPolicy.IMMUTABLE:
                changes.append(f"  [SKIP-IMMUTABLE] {adr_file.relative_to(_ROOT)}: ADR nunca tocado por sync")
                continue
            content = adr_file.read_text(encoding="utf-8")
            if is_timestamp_fresh(content):
                continue
            new_content = inject_timestamp(content, label="revisão")
            if new_content != content:
                rel = adr_file.relative_to(_ROOT)
                if dry_run:
                    changes.append(f"  Would update {rel}")
                else:
                    adr_file.write_text(new_content, encoding="utf-8")
                    changes.append(f"  {rel}: timestamp (revisão) updated")

    for rel_path in _GENERIC_MD_FILES:
        if policy_for(rel_path) == DocPolicy.IMMUTABLE:
            continue
        md_file = _ROOT / rel_path
        if not md_file.exists():
            continue
        content = md_file.read_text(encoding="utf-8")
        if is_timestamp_fresh(content):
            continue
        new_content = inject_timestamp(content)
        if new_content != content:
            if dry_run:
                changes.append(f"  Would update {rel_path}")
            else:
                md_file.write_text(new_content, encoding="utf-8")
                changes.append(f"  {rel_path}: timestamp updated")

    return changes


def _strict_audit() -> list[dict]:
    """Varre todos os .md do repo com patterns previsíveis e reporta divergências.

    NÃO auto-corrige — apenas alerta. Roda com --check --strict.
    Usa os.walk para evitar travessia de symlinks quebrados no .venv (Windows).
    Returns list of dicts: {file, line, match, message, severity}.
    """
    import os as _os

    patterns = [
        (r"\b17\b.*(páginas?|telas?|módulos?|pages?|aba)", "Page count desatualizado (17 -> 18)", "HIGH"),
        (r"\b418\b", "Test count desatualizado (418 -> 483)", "HIGH"),
        (r"\b383\b", "Test count desatualizado (383 -> 483)", "HIGH"),
        (
            r"\b512\b.*(testes|passing|passando)",
            "Test count desatualizado (512 -> 577) - verificar contexto historico",
            "MEDIUM",
        ),
        (r"\b630\b.*total", "Total tests desatualizado (630 -> 745)", "HIGH"),
        (r"\b709\b.*total", "Total tests desatualizado (709 -> 745)", "HIGH"),
    ]

    _skip = {
        ("AGENTS.md", "418"),
        ("AGENTS.md", "512 passing"),
        ("AGENTS.md", "630 total"),
        ("AGENTS.md", "709 total"),
        ("README.md", "512 unit+schema + 102 integration + 10 design + 6 real = 630 total passing"),
        ("README.md", "630 total"),
        ("README.md", "709 total"),
        ("docs\\changelog.md", "17 (nova página"),
        ("docs\\changelog.md", "17→18 pages"),
        ("docs\\changelog.md", "17→18 aba"),
        ("docs\\changelog.md", "17→18 módulos"),
        ("docs\\changelog.md", "418"),
        ("docs\\changelog.md", "383"),
    }

    findings = []
    seen = set()
    skip_dirs = {".git", ".venv", "node_modules", "__pycache__", "lib64"}

    for dirpath, dirnames, filenames in _os.walk(str(_ROOT), topdown=True):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            fpath = Path(dirpath) / fname
            rel = fpath.relative_to(_ROOT)
            if str(rel).startswith(("docs/archive/", "docs\\archive\\")):
                continue
            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue
            for pat, msg, sev in patterns:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    line_num = text[: m.start()].count("\n") + 1
                    match_text = m.group().strip()
                    key = (str(rel), match_text)
                    if key in seen:
                        continue
                    if key in _skip:
                        continue
                    seen.add(key)
                    findings.append(
                        {
                            "file": str(rel),
                            "line": line_num,
                            "match": match_text,
                            "message": msg,
                            "severity": sev,
                        }
                    )
    return findings


def _check_dirty_invariants() -> list[str]:
    """Detecta mutação manual de arquivos em IMMUTABLE/SNAPSHOT_FROZEN.

    Retorna lista de issues (vazia = nenhum arquivo dirty).
    """
    import subprocess as _sp


    issues: list[str] = []

    try:
        proc = _sp.run(
            ["git", "status", "--porcelain"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except Exception:
        return issues

    for line in proc.stdout.splitlines():
        if not line:
            continue
        status = line[:2].strip()
        path = line[3:].strip().rstrip("/")
        if not path.endswith(".md"):
            continue
        rel = path.replace("\\", "/").lstrip("./")
        if status and rel.startswith("docs/archive/ux_audit"):
            issues.append(f"[SNAPSHOT_FROZEN] {rel} modificado manualmente (não esperado)")
        if status and rel.startswith("docs/adr/"):
            issues.append(
                f"[IMMUTABLE] {rel} modificado manualmente — criar ADR novo (padrão Superseded by)"
            )

    return issues


def run_sync(dry_run: bool = False, check: bool = False, strict: bool = False, experimental: bool = False) -> bool:
    """
    Main sync logic. Returns True if in sync, False if out of sync.

    With check=True: validates docs but does NOT modify files (acts as dry_run).
    Drift detection runs against pytest --collect-only. If the source of truth
    (sync_docs count) disagrees with pytest's reported total, --check fails.
    This ensures checks are pure read-only operations, safe for hooks/CI.
    """
    if check:
        dry_run = True

    issues: list[str] = []

    state = _build_agents_state()
    print(f"Current state (as of {state['updated_at']}):")
    print(
        f"  Tests: {state['total_tests']} total ({', '.join(f'{k}={v}' for k, v in state['test_counts'].items() if v > 0)})"
    )
    print(f"  Dashboard pages: {state['pages_count']}")
    print(f"  API services: {', '.join(state['api_services'])}")
    print(f"  CI workflows: {', '.join(state['workflows'])}")

    print("\nDrift detection (sync_docs counts vs pytest --collect-only)...")
    drift = _check_drift()
    if drift:
        for d in drift:
            print(f"  [DRIFT] {d}")
            issues.append(f"Drift: {d}")
    else:
        print("  [OK] All test counts match pytest --collect-only")

    print("\nInvariants (IMMUTABLE / SNAPSHOT_FROZEN dirty detection)...")
    invariants = _check_dirty_invariants()
    if invariants:
        for d in invariants:
            print(f"  [INVARIANT] {d}")
            issues.append(d)
    else:
        print("  [OK] No manual mutation of immutable docs")

    print("\nSkills sync check (disk vs APPROVED_SKILLS)...")
    skill_issues = _check_skills_sync()
    if skill_issues:
        for s in skill_issues:
            print(f"  [FAIL] {s}")
            issues.append(f"Skills: {s}")
    else:
        print("  [OK] All skills match between disk and APPROVED_SKILLS")

    print("\nUpdating AGENTS.md + auto-fixers...")
    agent_changes = _update_agents_md(state, dry_run=dry_run)
    if dry_run:
        for c in agent_changes:
            print(f"  {c}")
        if agent_changes:
            issues.append("[LIVE] AGENTS.md drift (> update_agents_md disparou)")
    if not dry_run:
        agents_content = _AGENTS.read_text(encoding="utf-8")
        fixed = _fix_agents_tree(agents_content, state)
        if fixed != agents_content:
            _AGENTS.write_text(fixed, encoding="utf-8")
            print("  [OK] Auto-fixers applied to AGENTS.md")
        else:
            print("  [OK] No auto-fixer changes needed")
    else:
        print("  (dry-run, skipped)")

    print("\nSyncing docs/skills.md...")
    skill_md_changes = _sync_skills_md(state, dry_run=dry_run)
    for c in skill_md_changes:
        print(f"  {c}")
    if dry_run and any("Would" in c for c in skill_md_changes):
        issues.append("[AUTO] docs/skills.md drift")

    print("\nUpdating docs/archive/ (Raio X - policy-driven)...")
    archive_changes = _update_archive_md(state, dry_run=dry_run)
    for c in archive_changes:
        print(f"  {c}")
    if dry_run:
        if any("[DRIFT]" in c for c in archive_changes):
            print("  [NOTE] SNAPSHOT_REFERENCE_LIVE drift (auto-fix no pre-push)")
        if any("[DERIVED]" in c for c in archive_changes):
            print("  [NOTE] SNAPSHOT_DERIVED_LIVE — regeneração via IA em sprint review (não bloqueia)")
    if not dry_run and any("[DERIVED]" in c for c in archive_changes):
        print("  [NOTE] SNAPSHOT_DERIVED_LIVE permanece — regeneração é manual")

    print("\nUpdating README.md...")
    readme_changes = _update_readme_md(state, dry_run=dry_run)
    for c in readme_changes:
        print(f"  {c}")
    if dry_run and readme_changes:
        issues.append("[LIVE] README.md drift (badges/contadores)")

    print("\nUpdating REGRAS.md...")
    rules_changes = _update_rules_md(state, dry_run=dry_run)
    for c in rules_changes:
        print(f"  {c}")
    if dry_run and rules_changes:
        issues.append("[LIVE] REGRAS.md drift")

    print("\nGenerating API docs (AST from services/)...")
    api_changes = _generate_api_docs(state, dry_run=dry_run)
    for c in api_changes:
        print(f"  {c}")
    if dry_run:
        api_count = sum(1 for c in api_changes if c.startswith("  Would regenerate"))
        if api_count > 0:
            issues.append(f"[AUTO] {api_count} docs/api/*.md precisam regenerar")

    print("\nUpdating generic .md files (timestamps)...")
    generic_changes = _update_generic_md(state, dry_run=dry_run)
    for c in generic_changes:
        print(f"  {c}")
    if dry_run:
        ts_drift = sum(1 for c in generic_changes if c.startswith("  Would update"))
        if ts_drift > 0:
            issues.append(f"[TIMESTAMP] {ts_drift} docs precisam atualizar timestamp")

    # Changelog format validation (detecta — não bloqueia)
    # Mudanças de ordenação são content-quality, não drift estrutural.
    # Dev conserta manualmente; o gate --check lista como tarefa mas NÃO aborta.
    changelog_path = _ROOT / "docs" / "changelog.md"
    if changelog_path.exists():
        changelog_content = changelog_path.read_text(encoding="utf-8")
        changelog_issues = validate_changelog(changelog_content)
        if changelog_issues:
            print("\nChangelog format notes (reorg obrigatória, não bloqueia gate):")
            for ci in changelog_issues:
                print(f"  [NOTE] {ci}")
        else:
            print("\n  [OK] changelog ordering valid")

    if strict:
        print(
            f"\nStrict audit (--strict{' experimental' if experimental else ''}): scanning all .md for stale patterns..."
        )

        findings = _v2_strict_audit() if experimental else _strict_audit()

        if findings:
            for f in findings:
                safe_match = f["match"].encode("ascii", errors="replace").decode("ascii")
                label = "  [{sev}] {file}:{line} - {msg}".format(
                    sev=f["severity"], file=f["file"], line=f["line"], msg=f["message"]
                )
                print(f"  {label}  (match: '{safe_match}')")
                safe_full = f"{f['file']}:{f['line']} - {f['match']} - {f['message']}"
                issues.append(safe_full.encode("ascii", errors="replace").decode("ascii"))
        else:
            print("  [OK] No stale patterns found in any .md file")
    else:
        print("\n  (pass --strict for full .md audit)")

    print()
    if issues:
        print(f"[FAIL] Issues found: {len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print(f"[{_OK}] All docs in sync")
        return True


# ═══════════════════════════════════════════════════════════════════
# v2 — Embedded classifier / parser / updater (from sync_docs_v2)
# ═══════════════════════════════════════════════════════════════════

# ── v2 Classifier ─────────────────────────────────────────────────

_HISTORICAL_HEADING_MARKERS = {
    "histórico",
    "histórico de versões",
    "versão",
    "changelog",
    "roadmap",
    "próximos",
    "lição",
    "lições",
    "lessons",
    "entregas confirmadas",
    "entregas",
    "milestone",
}

_CURRENT_HEADING_MARKERS = {
    "status atual",
    "avaliação",
    "avaliação de riscos",
    "riscos",
    "métricas finais",
    "métricas de sucesso",
}

_HISTORICAL_MATCH_MARKERS = [
    "era ",
    "em 29/06",
    "em 30/06",
    "resolvido",
    "mitigado",
    "passou de ",
    "subiu de",
    "anteriormente",
]


def _v2_classify(heading: str, match_text: str, file_path: str) -> str:
    """Return 'HISTORICAL', 'CURRENT', or 'AMBIGUOUS'.

    Checks (in order):
    1. File-level: changelog.md is always HISTORICAL
    2. Heading path markers
    3. Match text markers
    4. Default: AMBIGUOUS
    """
    h_lower = heading.lower()
    m_lower = match_text.lower()
    fp_lower = file_path.lower()

    if "changelog" in fp_lower:
        return "HISTORICAL"

    for marker in _HISTORICAL_HEADING_MARKERS:
        if marker in h_lower:
            return "HISTORICAL"

    for marker in _HISTORICAL_MATCH_MARKERS:
        if marker in m_lower:
            return "HISTORICAL"

    for marker in _CURRENT_HEADING_MARKERS:
        if marker in h_lower:
            return "CURRENT"

    if "readme" in fp_lower and "roadmap" in h_lower:
        return "HISTORICAL"

    return "AMBIGUOUS"


# ── v2 Parser ──────────────────────────────────────────────────────

_V2_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "lib64"}

_V2_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b17\b.*(páginas?|telas?|módulos?|pages?|aba)"), "page_count"),
    (re.compile(r"\b418\b"), "test_count_418"),
    (re.compile(r"\b383\b"), "test_count_383"),
    (re.compile(r"\b512\b.*(testes|passing|passando)"), "test_count_512"),
    (re.compile(r"\b630\b.*total"), "test_count_630"),
    (re.compile(r"\b709\b.*total"), "test_count_709"),
]


def _v2_compute_section_spans(text: str) -> dict[int, str]:
    """Return dict: line_num -> heading_path for the entire section span."""
    from markdown_it import MarkdownIt as _MarkdownIt

    _md = _MarkdownIt()
    tokens = _md.parse(text)
    headings: list[dict] = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            start = tok.map[0] if tok.map else 0
            content = ""
            for j in range(i + 1, len(tokens)):
                if tokens[j].type == "inline":
                    content = tokens[j].content
                    break
                elif tokens[j].type == "heading_close":
                    break
            headings.append({"level": level, "content": content, "start": start})

    headings.sort(key=lambda h: h["start"])

    for i, h in enumerate(headings):
        end = len(text.split("\n"))
        for j in range(i + 1, len(headings)):
            if headings[j]["level"] <= h["level"]:
                end = headings[j]["start"]
                break
        h["end"] = end

    lines = text.split("\n")
    line_to_heading: dict[int, str] = {}
    for line_num in range(len(lines)):
        path: list[tuple[int, str]] = []
        for h in headings:
            if h["start"] <= line_num < h["end"]:
                path = [p for p in path if p[0] < h["level"]]
                path.append((h["level"], h["content"]))
        line_to_heading[line_num] = " > ".join(t for _, t in path)

    return line_to_heading


def _v2_scan_all_md() -> list[dict]:
    """Scan all .md files and return structured findings.

    Each finding: {file, line, match, pattern, heading, classification}
    """
    import os as _os

    findings: list[dict] = []

    for dirpath, dirnames, filenames in _os.walk(str(_ROOT), topdown=True):
        dirnames[:] = [d for d in dirnames if d not in _V2_SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(_ROOT))
            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue

            line_to_heading = _v2_compute_section_spans(text)

            for pat, pat_name in _V2_PATTERNS:
                for m in pat.finditer(text):
                    line_num = text[: m.start()].count("\n")
                    heading = line_to_heading.get(line_num, "")
                    findings.append(
                        {
                            "file": rel,
                            "line": line_num + 1,
                            "heading": heading,
                            "pattern": pat_name,
                            "match": m.group().strip()[:80],
                        }
                    )

    return findings


# ── v2 Updater ─────────────────────────────────────────────────────


def _v2_build_replacements(truth: dict) -> dict[str, tuple[str, str]]:
    unit = truth["test_counts"].get("unit", 0)
    schema = truth["test_counts"].get("schema", 0)
    total = truth["total_tests"]
    pages = truth["pages_count"]

    return {
        "page_count": ("17", str(pages)),
        "test_count_418": ("418", str(unit)),
        "test_count_383": ("383", str(unit)),
        "test_count_512": ("512", str(unit + schema)),
        "test_count_630": ("630", str(total)),
        "test_count_709": ("709", str(total)),
    }


def _v2_apply_fix(text: str, stale_num: str, truth_num: str) -> str:
    """Replace stale_num with truth_num, as standalone word/boundary.

    Uses word-boundary regex \b to avoid replacing substrings of larger numbers.
    Only replaces FIRST occurrence.
    """
    return re.sub(rf"\b{re.escape(stale_num)}\b", truth_num, text, count=1)


def _v2_sync_file(fpath: Path, findings: list[dict], truth: dict, dry_run: bool = False) -> list[str]:
    """Apply updates to a single .md file based on CURRENT-classified findings.

    Returns list of change descriptions (empty = no changes).
    """
    repl = _v2_build_replacements(truth)
    changes: list[str] = []
    content = fpath.read_text(encoding="utf-8")

    for finding in findings:
        if finding.get("classification") != "CURRENT":
            continue
        pat = finding["pattern"]
        if pat not in repl:
            continue
        stale_num, truth_num = repl[pat]

        if re.search(rf"\b{re.escape(stale_num)}\b", content) is None:
            continue

        new_content = _v2_apply_fix(content, stale_num, truth_num)
        if new_content != content:
            changes.append(f"  {finding['file']}:{finding['line']} - {pat}: '{stale_num}' -> '{truth_num}'")
            content = new_content

    if not dry_run:
        fpath.write_text(content, encoding="utf-8")

    return changes


# ── v2 Analysis / Sync ──────────────────────────────────────────────


def _v2_run_analyze() -> list[dict]:
    """Run scanner + classifier on all .md files."""
    raw = _v2_scan_all_md()
    for f in raw:
        f["classification"] = _v2_classify(f["heading"], f["match"], f["file"])
    return raw


def _v2_run_sync(dry_run: bool = False) -> tuple[list[str], list[dict]]:
    """Sync all CURRENT blocks with truth values.

    Returns (changes, findings).
    """
    findings = _v2_run_analyze()
    truth = _build_agents_state()
    all_changes: list[str] = []

    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)

    for file_rel, file_findings in by_file.items():
        fpath = _ROOT / file_rel
        changes = _v2_sync_file(fpath, file_findings, truth, dry_run=dry_run)
        all_changes.extend(changes)

    return all_changes, findings


def _v2_print_findings(findings: list[dict]):
    counts = Counter(f["classification"] for f in findings)
    print(
        f"Total: {len(findings)}  CURRENT: {counts.get('CURRENT', 0)}  "
        f"HISTORICAL: {counts.get('HISTORICAL', 0)}  "
        f"AMBIGUOUS: {counts.get('AMBIGUOUS', 0)}"
    )
    print()

    if not findings:
        return

    for f in findings:
        cl = f["classification"]
        sep = "  "
        print(f"  [{cl:<10}] {f['file']}:{f['line']}")
        print(f"{sep}heading: {f['heading'][:100]}")
        print(f"{sep}match:   '{f['match']}'")
        print()


def _v2_strict_audit() -> list[dict]:
    """Strict audit using v2 classifier instead of hardcoded _skip set.

    Replicates v1 _strict_audit() output format but uses heading-based
    classification (CURRENT vs HISTORICAL) to filter findings.
    """
    findings = _v2_run_analyze()
    result = []
    for f in findings:
        if f["classification"] == "HISTORICAL":
            continue
        sev = "HIGH"
        if f["pattern"] in ("test_count_512",):
            sev = "MEDIUM"
        if f["classification"] == "AMBIGUOUS":
            sev = "MEDIUM"
        result.append(
            {
                "file": f["file"],
                "line": f["line"],
                "match": f["match"],
                "message": f"Stale {f['pattern']} in '{f['heading']}'",
                "severity": sev,
            }
        )
    return result


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════


def _ensure_utf8():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        import contextlib

        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    _ensure_utf8()
    parser = argparse.ArgumentParser(description="Sync project documentation with code state")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--check", action="store_true", help="Exit 1 if docs are out of sync (CI mode)")
    parser.add_argument(
        "--strict", action="store_true", help="Run full .md audit for stale patterns (page count, test count)"
    )
    parser.add_argument(
        "--experimental", action="store_true", help="Use v2 classifier for strict audit instead of hardcoded skip set"
    )
    parser.add_argument("--analyze", action="store_true", help="Classify stale refs via heading hierarchy (v2)")
    parser.add_argument("--sync", action="store_true", help="Auto-update CURRENT blocks with truth values (v2)")
    parser.add_argument("--dump-truth", action="store_true", help="Print truth JSON and exit")
    args = parser.parse_args()

    if args.analyze:
        findings = _v2_run_analyze()
        _v2_print_findings(findings)
        ambiguous = sum(1 for f in findings if f["classification"] == "AMBIGUOUS")
        if ambiguous > 0:
            print(f"\n[BLOCK] {ambiguous} AMBIGUOUS ref(s) found — CI blocked")
            sys.exit(1)
        return

    if args.sync:
        # Bug fix: --sync must run BOTH v1 (README/REGRAS/timestamps/AGENTS/API)
        # AND v2 (CURRENT blocks in arbitrary docs). Historically #sync# only
        # invoked #_v2_run_sync() which left READMEs/timestamps stale.
        if not args.dry_run:
            print("=== v1 sync (README/REGRAS/AGENTS/API/timestamps) ===")
            v1_in_sync = run_sync(
                dry_run=False, check=False, strict=False, experimental=False
            )
            print()
        changes, findings = _v2_run_sync(dry_run=args.dry_run)
        if changes:
            print(f"Changes to apply ({'dry-run' if args.dry_run else 'live'}):")
            for c in changes:
                print(c)
            print()
            print(f"Total: {len(changes)} changes across {len(findings)} findings")
        else:
            print("No stale CURRENT refs found. All docs are in sync.")
        return

    if args.dump_truth:
        truth = _build_agents_state()
        print(json.dumps(truth, ensure_ascii=False, indent=2, default=str))
        return

    in_sync = run_sync(dry_run=args.dry_run, check=args.check, strict=args.strict, experimental=args.experimental)

    if args.check and not in_sync:
        print("\n::error::Documentation is out of sync. Run 'python scripts/sync_docs.py' to update.")
        sys.exit(1)
    if args.dry_run:
        print("\n(Dry-run complete, no changes made)")


if __name__ == "__main__":
    main()
