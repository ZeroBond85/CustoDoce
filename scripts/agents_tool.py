"""
agents_tool.py — Gestão do AGENTS.md + documentação.

Uso:
    python scripts/agents_tool.py --check         # Valida schema
    python scripts/agents_tool.py --full          # Validação completa (CI mode)
    python scripts/agents_tool.py --status        # Estado atual
    python scripts/agents_tool.py --add-rule      # Adicionar regra no top 10
    python scripts/agents_tool.py --add-lesson    # Adicionar lição no LESSONS.md
"""

from __future__ import annotations

import argparse
import contextlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "AGENTS.md"
LESSONS = ROOT / "LESSONS.md"
SCHEMA = ROOT / "config" / "agents_schema.yaml"
REGRAS = ROOT / "REGRAS.md"
SKILLS = ROOT / "docs" / "skills.md"
LESSONS_SCHEMA = ROOT / "config" / "lessons_schema.yaml"
REGRAS_SCHEMA = ROOT / "config" / "regras_schema.yaml"


def load_schema() -> dict:
    """Load schema from YAML (simple parser, no deps)."""
    if not SCHEMA.exists():
        return {}
    text = SCHEMA.read_text(encoding="utf-8")
    result: dict = {"max_lines": 999, "headings": {}, "blocked_heading_patterns": {}}
    current_section = None
    current_key = None
    for line in text.splitlines():
        if line.startswith("max_lines:"):
            val = line.split(":", 1)[1].strip()
            with contextlib.suppress(ValueError):
                result["max_lines"] = int(val)
        elif line.startswith("headings:"):
            current_section = "headings"
        elif line.startswith("blocked_heading_patterns:"):
            current_section = "blocked"
        elif line.startswith("allow_new_headings:"):
            result["allow_new"] = line.split(":", 1)[1].strip() == "true"
        elif current_section == "headings" and line.startswith("  ") and ":" in line:
            candidate = line.strip().rstrip(":")
            if (
                candidate
                and not candidate.startswith("type")
                and not candidate.startswith("max")
                and not candidate.startswith("description")
                and not candidate.startswith("mandatory")
                and not candidate.startswith("auto")
                and not candidate.startswith("allow")
            ):
                current_key = candidate
                result["headings"][current_key] = {}
            elif candidate.startswith("type ") or candidate == "type":
                val = line.split(":", 1)[1].strip()
                if current_key and current_key in result["headings"]:
                    result["headings"][current_key]["type"] = val
            elif candidate.startswith("max_lines ") or candidate == "max_lines":
                val = line.split(":", 1)[1].strip()
                if current_key and current_key in result["headings"]:
                    with contextlib.suppress(ValueError):
                        result["headings"][current_key]["max_lines"] = int(val)
            elif candidate.startswith("mandatory ") or candidate == "mandatory":
                val = line.split(":", 1)[1].strip()
                if current_key and current_key in result["headings"]:
                    result["headings"][current_key]["mandatory"] = val == "true"
            elif candidate.startswith("auto_generated ") or candidate == "auto_generated":
                val = line.split(":", 1)[1].strip()
                if current_key and current_key in result["headings"]:
                    result["headings"][current_key]["auto_generated"] = val == "true"
            elif candidate.startswith("allow_key ") or candidate == "allow_key":
                val = line.split(":", 1)[1].strip().strip("\"'")
                if current_key and current_key in result["headings"]:
                    result["headings"][current_key]["allow_key"] = val
        elif current_section == "blocked" and line.startswith("  ") and ":" in line:
            key = line.split(":", 1)[0].strip()
            val_line = line.split(":", 1)[1].strip()
            if val_line.startswith("{") and "target" in val_line:
                target_match = re.search(r'target:\s*"([^"]+)"', val_line)
                reason_match = re.search(r'reason:\s*"([^"]+)"', val_line)
                if target_match and reason_match:
                    result["blocked_heading_patterns"][key] = {
                        "target": target_match.group(1),
                        "reason": reason_match.group(1),
                    }
    return result


def load_lessons_schema() -> dict:
    """Load lessons schema from YAML."""
    if not LESSONS_SCHEMA.exists():
        return {}
    result: dict = {"max_lines": 700, "no_duplicates": True, "monotonic": True, "checkable": True}
    text = LESSONS_SCHEMA.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("max_lines:"):
            with contextlib.suppress(ValueError):
                result["max_lines"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("no_duplicates:"):
            result["no_duplicates"] = line.split(":", 1)[1].strip() == "true"
        elif line.startswith("monotonic:"):
            result["monotonic"] = line.split(":", 1)[1].strip() == "true"
        elif line.startswith("checkable:"):
            result["checkable"] = line.split(":", 1)[1].strip() == "true"
    return result


def load_regras_schema() -> dict:
    """Load regras schema from YAML."""
    if not REGRAS_SCHEMA.exists():
        return {}
    result: dict = {"pre_commit_layers": 0, "layer_names": []}
    text = REGRAS_SCHEMA.read_text(encoding="utf-8")
    current_list = None
    for line in text.splitlines():
        if line.startswith("pre_commit_layers:"):
            with contextlib.suppress(ValueError):
                result["pre_commit_layers"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("layer_names:"):
            current_list = "layer_names"
        elif current_list == "layer_names" and line.strip().startswith("- "):
            result["layer_names"].append(line.strip()[2:].strip().strip('"'))
        elif current_list and not line.strip().startswith("- "):
            current_list = None
    return result


def get_heading_key(heading: str) -> str:
    """Normalize heading text to schema key."""
    h = heading.lower().strip()
    h = re.sub(r"[^a-z0-9]+", "_", h)
    h = h.strip("_")
    if not h:
        return "unknown"
    return h


def find_headings(content: str) -> list[dict]:
    """Find all ## headings with line numbers and content."""
    results = []
    lines = content.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^## (.+)", line)
        if m:
            results.append({"heading": m.group(1).strip(), "line": i + 1, "start": i})
    return results


def check_schema() -> list[str]:
    """Validate AGENTS.md against schema. Return list of issues (empty = ok)."""
    issues: list[str] = []
    if not AGENTS.exists():
        issues.append("AGENTS.md nao encontrado")
        return issues

    content = AGENTS.read_text(encoding="utf-8")
    lines = content.splitlines()
    schema = load_schema()

    # Check max lines
    max_lines = schema.get("max_lines", 999)
    if len(lines) > max_lines:
        issues.append(f"AGENTS.md tem {len(lines)} linhas (max {max_lines})")

    # Check headings
    heading_patterns = schema.get("blocked_heading_patterns", {})
    headings = find_headings(content)

    for h in headings:
        hl = h["heading"].lower()
        blocked = False
        for pattern, info in heading_patterns.items():
            if pattern.lower() in hl:
                issues.append(
                    f"Heading '{h['heading']}' (linha {h['line']}) contem '{pattern}' "
                    f"— bloqueado: {info.get('reason', '')}. "
                    f"Destino: {info.get('target', '?')}"
                )
                blocked = True
                break
        if not blocked:
            hkey = get_heading_key(h["heading"])
            if hkey not in schema.get("headings", {}) and not schema.get("allow_new", False):
                issues.append(
                    f"Heading '{h['heading']}' (linha {h['line']}) nao esta na allowlist. "
                    f"Adicione em config/agents_schema.yaml ou mova para outro arquivo."
                )

            # Check max_lines per section
            for schema_key, schema_heading in schema.get("headings", {}).items():
                max_sec = schema_heading.get("max_lines", 999)
                if hkey == schema_key or hkey == schema_heading.get("allow_key"):
                    sec_start = h["start"]
                    # find next heading
                    all_heads = find_headings(content)
                    sec_end = len(lines)
                    for next_h in all_heads:
                        if next_h["line"] > h["line"]:
                            sec_end = next_h["start"] - 1
                            break
                    sec_len = sec_end - sec_start
                    if sec_len > max_sec:
                        issues.append(f"Secao '{h['heading']}' tem {sec_len} linhas (max {max_sec})")
                    break

    # Check mandatory headings
    for schema_key, schema_heading in schema.get("headings", {}).items():
        if schema_heading.get("mandatory"):
            found = False
            for h in headings:
                hkey = get_heading_key(h["heading"])
                if hkey == schema_key or hkey == schema_heading.get("allow_key"):
                    found = True
                    break
            if not found:
                issues.append(f"Heading mandatorio '{schema_key}' nao encontrado em AGENTS.md")

    return issues


def run_v2_analyze() -> list[str]:
    """Run sync_docs_v2 --analyze. Return list of issues (empty = ok)."""
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/sync_docs.py"), "--analyze"],
            capture_output=True,
            text=False,
            cwd=str(ROOT),
            timeout=30,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        if result.returncode != 0:
            stderr_text = stderr[:500] if stderr else stdout[-1000:]
            return [f"V2 --analyze falhou (exit {result.returncode}): {stderr_text}"]
        if "BLOCK" in stdout:
            return [f"V2 --analyze reportou AMBIGUOUS:\n{stdout[-1000:]}"]
        return []
    except subprocess.TimeoutExpired:
        return ["V2 --analyze timeout (30s)"]
    except Exception as e:
        return [f"V2 --analyze erro: {e}"]


def run_sync_docs() -> list[str]:
    """Run sync_docs_v1 --check --strict. Return issues."""
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/sync_docs.py"), "--check", "--strict"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=60,
        )
        issues = []
        if result.returncode != 0:
            issues.append(f"sync_docs --check --strict falhou (exit {result.returncode})")
        for line in result.stdout.splitlines():
            if "FAIL" in line or "DRIFT" in line or "BLOCK" in line:
                issues.append(line.strip())
        return issues
    except subprocess.TimeoutExpired:
        return ["sync_docs timeout (60s)"]
    except Exception as e:
        return [f"sync_docs erro: {e}"]


def show_status() -> str:
    """Show current state of AGENTS.md and related docs."""
    parts = []
    if AGENTS.exists():
        content = AGENTS.read_text(encoding="utf-8")
        lines = content.splitlines()
        headings = find_headings(content)
        parts.append(f"AGENTS.md: {len(lines)} linhas, {len(headings)} secoes")
        for h in headings[:5]:
            parts.append(f"  - {h['heading']}")
        if len(headings) > 5:
            parts.append(f"  ... +{len(headings) - 5} secoes")
    else:
        parts.append("AGENTS.md: nao encontrado")

    for name, path in [("LESSONS.md", LESSONS), ("REGRAS.md", REGRAS)]:
        if path.exists():
            c = path.read_text(encoding="utf-8")
            parts.append(f"{name}: {len(c.splitlines())} linhas")
        else:
            parts.append(f"{name}: nao existe")

    # Count other .md files (with error handling for Windows symlinks)
    md_files: list[Path] = []
    skip_dirs = {".git", ".venv", "node_modules", "__pycache__"}
    try:
        for p in ROOT.rglob("*.md"):
            if not any(s in str(p) for s in skip_dirs):
                md_files.append(p)
    except (OSError, PermissionError):
        pass
    parts.append(f"Total .md no repo: {len(md_files)}")

    return "\n".join(parts)


def add_rule(title: str, body: str) -> str:
    """Add a rule to the top 10 in AGENTS.md."""
    if not AGENTS.exists():
        return "AGENTS.md nao encontrado"
    content = AGENTS.read_text(encoding="utf-8")
    # Check if "## Regras Mandatórias" exists
    if "## Regras Mandatórias" not in content:
        # Add after the title
        new_section = (
            "## Regras Mandatórias\n\n"
            "Estas regras NUNCA podem ser removidas. CI valida presença.\n\n"
            f"1. **{title}**: {body}\n"
        )
        # Insert after first line (# title)
        first_nl = content.index("\n")
        content = content[:first_nl] + "\n\n" + new_section + content[first_nl:]
        AGENTS.write_text(content, encoding="utf-8")
        return f"Regra '{title}' adicionada ao AGENTS.md (nova secao criada)"
    else:
        # Find the section and append
        m = re.search(r"(## Regras Mandatórias[^\n]*\n.+?)(?=\n## )", content, re.DOTALL)
        if m:
            # Count existing rules
            rules_section = m.group(1)
            existing = len(re.findall(r"^\d+\.", rules_section, re.MULTILINE))
            new_num = existing + 1
            insert_pos = m.end()
            new_rule = f"\n{new_num}. **{title}**: {body}"
            content = content[:insert_pos] + new_rule + content[insert_pos:]
            AGENTS.write_text(content, encoding="utf-8")
            return f"Regra '{title}' adicionada como #{new_num} no top 10"
        return "Nao foi possivel localizar secao de regras"


def add_lesson(title: str, body: str) -> str:
    """Add a lesson to LESSONS.md."""
    if not LESSONS.exists():
        LESSONS.write_text("# Lições Aprendidas\n\n", encoding="utf-8")

    content = LESSONS.read_text(encoding="utf-8")
    # Find highest lesson number (both ### and ## formats)
    nums = [int(m) for m in re.findall(r"^#{2,3} (\d+)\.", content, re.MULTILINE)]
    next_num = max(nums) + 1 if nums else 1

    new_lesson = f"\n### {next_num}. {title}\n\n{body}\n"
    LESSONS.write_text(content + new_lesson, encoding="utf-8")
    return f"Lição #{next_num} adicionada ao LESSONS.md"


def validate_lessons(content: str | None = None) -> list[str]:
    """Validate LESSONS.md against schema."""
    issues: list[str] = []
    if content is None:
        if not LESSONS.exists():
            issues.append("LESSONS.md nao encontrado")
            return issues
        content = LESSONS.read_text(encoding="utf-8")
    lines = content.splitlines()
    schema = load_lessons_schema()

    # Check max_lines
    max_lines = schema.get("max_lines", 700)
    if len(lines) > max_lines:
        issues.append(f"LESSONS.md tem {len(lines)} linhas (max {max_lines})")

    # Find all lesson headings (### or ## with number)
    lesson_heads = []
    for i, line in enumerate(lines):
        m = re.match(r"^#{2,3} (\d+)\.", line)
        if m:
            lesson_heads.append({"num": int(m.group(1)), "line": i + 1, "text": line.strip()})

    if not lesson_heads:
        issues.append("Nenhuma licao encontrada em LESSONS.md")
        return issues

    # Check format: must be ### not ##
    for h in lesson_heads:
        if h["text"].startswith("## "):
            issues.append(
                f"Licao #{h['num']} (linha {h['line']}) usa '## ' em vez de '### '"
            )

    if not schema.get("checkable", True):
        return issues

    # Check no duplicates
    if schema.get("no_duplicates", True):
        seen: set[int] = set()
        for h in lesson_heads:
            if h["num"] in seen:
                matching = [x for x in lesson_heads if x["num"] == h["num"]]
                lines_str = ", ".join(f"L{x['line']}" for x in matching)
                issues.append(f"Licao #{h['num']} duplicada ({lines_str})")
            seen.add(h["num"])

    # Check monotonic order (warning only, non-blocking)
    if schema.get("monotonic", True):
        prev_num = 0
        for h in lesson_heads:
            if h["num"] < prev_num:
                print(
                    f"  [WARN] Ordem monotônica quebrada: #{h['num']} (linha {h['line']}) depois de #{prev_num}",
                    file=sys.stderr,
                )
            prev_num = h["num"]

    return issues


def validate_regras(content: str | None = None) -> list[str]:
    """Validate REGRAS.md against schema (pre-commit layer parity)."""
    issues: list[str] = []
    if content is None:
        if not REGRAS.exists():
            issues.append("REGRAS.md nao encontrado")
            return issues
        content = REGRAS.read_text(encoding="utf-8")

    schema = load_regras_schema()
    expected = schema.get("pre_commit_layers", 0)
    if not expected:
        return issues

    # Find "Pre-commit Hook" section
    section_match = re.search(
        r"(?:## Pre-commit Hook|## Pre-commit|## Pre-commit Hook?\b).*?(?=\n## |\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        issues.append("Secao 'Pre-commit Hook' nao encontrada em REGRAS.md")
        return issues

    section = section_match.group(0)
    numbered_lines = re.findall(r"^\d+(?:\.\d+)?[\.\)]\s*\S", section, re.MULTILINE)
    actual_count = len(numbered_lines)

    if actual_count != expected:
        issues.append(
            f"REGRAS.md documenta {actual_count} camadas de pre-commit "
            f"(secao 'Pre-commit Hook'), mas schema espera {expected} "
            f"conforme config/regras_schema.yaml"
        )

    return issues


def run_full() -> tuple[bool, list[str]]:
    """Run full documentation validation."""
    all_issues: list[str] = []
    print("[1/6] Validando schema do AGENTS.md...", file=sys.stderr)
    schema_issues = check_schema()
    if schema_issues:
        for i in schema_issues:
            print(f"  [FAIL] {i}", file=sys.stderr)
        all_issues.extend(schema_issues)
    else:
        print("  [OK] Schema valido", file=sys.stderr)

    print("[2/6] Rodando sync_docs v1 (test counts, pages)...", file=sys.stderr)
    sync_issues = run_sync_docs()
    if sync_issues:
        for i in sync_issues:
            print(f"  [FAIL] {i}", file=sys.stderr)
        all_issues.extend(sync_issues)
    else:
        print("  [OK] sync_docs v1 ok", file=sys.stderr)

    print("[3/6] Rodando V2 --analyze (todos .md)...", file=sys.stderr)
    v2_issues = run_v2_analyze()
    if v2_issues:
        for i in v2_issues:
            print(f"  [FAIL] {i}", file=sys.stderr)
        all_issues.extend(v2_issues)
    else:
        print("  [OK] V2 --analyze ok", file=sys.stderr)

    print("[4/6] Validando LESSONS.md...", file=sys.stderr)
    lessons_issues = validate_lessons()
    if lessons_issues:
        for i in lessons_issues:
            print(f"  [FAIL] {i}", file=sys.stderr)
        all_issues.extend(lessons_issues)
    else:
        print("  [OK] LESSONS.md valido", file=sys.stderr)

    print("[5/6] Validando REGRAS.md...", file=sys.stderr)
    regras_issues = validate_regras()
    if regras_issues:
        for i in regras_issues:
            print(f"  [FAIL] {i}", file=sys.stderr)
        all_issues.extend(regras_issues)
    else:
        print("  [OK] REGRAS.md valido", file=sys.stderr)

    print("[6/6] Estado atual...", file=sys.stderr)
    status = show_status()
    for line in status.splitlines():
        print(f"  {line}", file=sys.stderr)

    ok = len(all_issues) == 0
    if ok:
        print("\n[OK] Documentacao completa e consistente.", file=sys.stderr)
    else:
        print(f"\n[FAIL] {len(all_issues)} problema(s) encontrado(s).", file=sys.stderr)
    return ok, all_issues


def main():
    parser = argparse.ArgumentParser(description="Gestao do AGENTS.md")
    parser.add_argument("--check", action="store_true", help="Validar schema do AGENTS.md")
    parser.add_argument("--full", action="store_true", help="Validacao completa da documentacao")
    parser.add_argument("--status", action="store_true", help="Estado atual")
    parser.add_argument("--add-rule", nargs=2, metavar=("TITULO", "CORPO"), help="Adicionar regra no top 10")
    parser.add_argument("--add-lesson", nargs=2, metavar=("TITULO", "CORPO"), help="Adicionar licao no LESSONS.md")
    args = parser.parse_args()

    if args.check:
        issues = check_schema()
        lessons_issues = validate_lessons()
        regras_issues = validate_regras()
        all_issues = issues + lessons_issues + regras_issues
        if all_issues:
            for i in all_issues:
                print(f"[FAIL] {i}")
            sys.exit(1)
        print("[OK] Schema valido")
        print("[OK] LESSONS.md valido")
        print("[OK] REGRAS.md valido")
        return

    if args.full:
        ok, issues = run_full()
        sys.exit(0 if ok else 1)
        return

    if args.status:
        print(show_status())
        return

    if args.add_rule:
        msg = add_rule(args.add_rule[0], args.add_rule[1])
        print(msg)
        return

    if args.add_lesson:
        msg = add_lesson(args.add_lesson[0], args.add_lesson[1])
        print(msg)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
