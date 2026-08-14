#!/usr/bin/env python3
"""Audit de coerência dos .md — gate de qualidade da documentação.

Usa como truth ÚNICA o `_build_agents_state()` do `scripts/sync_docs.py`
(sem duplicar números em JSON). Complementa com métricas que o sync_docs
não mede (camadas do pre-commit, skills no disco, merge-conflicts).

Modos:
  (default)             Relatório completo (baseline + divergências)
  --check               Exit 1 se houver divergência HIGH/MEDIUM (CI)
  --fix-timestamps      Re-injeta timestamps nos docs vivos (idempotente)
  --list                Só lista arquivos + status, sem checagens
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
from scripts.doc_utils import check_counters_against_truth, extract_counters_cited  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Diretórios que NUNCA são comparados com a verdade atual (histórico/imutável)
HISTORICAL_PREFIXES = ("docs/archive/", "docs/adr/")

# Reports raiz datados (snapshots históricos do momento) — contadores são
# verdades do passado e NÃO devem ser comparados com a truth atual.
HISTORICAL_FILES = {
    "SCRAPER_ANALYSIS_REPORT.md",
    "SECURITY_AUDIT_REPORT_2026-08.md",
}

# Merge-conflict markers: presença = arquivo corrompido por merge não resolvido
_MERGE_MARKERS = re.compile(r"^(<{7}|={7}|>{7})\s", re.MULTILINE)

# Camada no pre-commit: "# Layer 1:" / "# 1.5." / "# 2.5 DOC" (sem pontuação)
_LAYER_PAT = re.compile(r"^# (?:Layer )?(\d+(?:\.\d+)?)(?:[.: ])", re.MULTILINE)

# Contextos históricos legítimos para contadores de workflows/skills
# (mesma filosofia do _COUNTER_ALLOW do doc_utils).
_WORKFLOW_ALLOW: set[tuple[str, int]] = {
    ("README.md", 14),  # Sprint 5: "14 workflows auditados" (snapshot do momento)
}
_SKILLS_ALLOW: set[tuple[str, int]] = {}


def _truth() -> dict:
    """Truth real do projeto (fonte única: sync_docs)."""
    from scripts import sync_docs  # import tardio (suprime warnings do streamlit)

    state = sync_docs._build_agents_state()
    state["pre_commit_layers"] = _count_pre_commit_layers()
    state["skills_count"] = _count_skills()
    return state


def _count_pre_commit_layers() -> int:
    """Conta camadas no .githooks/pre-commit (Layer N / Layer N.N)."""
    hook = ROOT / ".githooks" / "pre-commit"
    if not hook.exists():
        return 0
    text = hook.read_text(encoding="utf-8")
    return len(set(_LAYER_PAT.findall(text)))


def _count_skills() -> int:
    """Conta skills instaladas (.opencode/skills/*/SKILL.md)."""
    skills_dir = ROOT / ".opencode" / "skills"
    if not skills_dir.exists():
        return 0
    return sum(1 for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


def _iter_live_mds():
    """Itera .md vivos (fora archive/adr). Retorna (Path, rel_norm)."""
    skip_dirs = {".git", "node_modules", "__pycache__", "lib64", ".agents"}
    for dirpath, dirnames, filenames in ROOT.walk():
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".venv")]
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            fpath = Path(dirpath) / fname
            rel = fpath.relative_to(ROOT)
            rel_norm = str(rel).replace("\\", "/")
            if rel_norm.startswith(HISTORICAL_PREFIXES):
                continue
            yield fpath, rel_norm


def _check_merge_conflicts() -> list[dict]:
    """Procura markers de merge não resolvido em qualquer .md do repo."""
    findings: list[dict] = []
    for dirpath, dirnames, filenames in ROOT.walk():
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "__pycache__", "lib64"} and not d.startswith(".venv")]
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(ROOT)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue
            for m in _MERGE_MARKERS.finditer(text):
                line_num = text[: m.start()].count("\n") + 1
                findings.append(
                    {
                        "file": rel,
                        "line": line_num,
                        "match": m.group().strip(),
                        "message": "Merge-conflict marker (git não resolvido)",
                        "severity": "HIGH",
                    }
                )
    return findings


def _audit_live() -> list[dict]:
    """Audita contadores citados + camadas/skills/workflows/lições nos docs vivos."""
    truth = _truth()
    findings: list[dict] = []
    unit = truth["test_counts"].get("unit", 0)
    schema = truth["test_counts"].get("schema", 0)
    real_total = unit + schema
    real_layers = truth["pre_commit_layers"]
    real_skills = truth["skills_count"]
    real_workflows = truth["workflows_count"]
    real_lessons = truth["lessons_count"]

    for fpath, rel_norm in _iter_live_mds():
        try:
            content = fpath.read_text(encoding="utf-8")
        except Exception:
            continue

        # LESSONS.md e changelog são histórico: contadores/camadas/skills citados
        # descrevem o estado DO MOMENTO, nunca a truth atual. Pula checagens de
        # conteúdo (a parity de lições é validada separadamente no AGENTS.md).
        is_historical_content = rel_norm in HISTORICAL_FILES or rel_norm in ("LESSONS.md", "docs/changelog.md")

        # Contadores de testes/páginas via doc_utils (respecta allowlist histórica)
        cited = extract_counters_cited(content)
        truth_with_rel = {**truth, "rel_path": rel_norm}
        for w in check_counters_against_truth(cited, truth_with_rel):
            if is_historical_content:
                continue
            findings.append({"file": rel_norm, "line": 0, "match": "", "message": w, "severity": "MEDIUM"})

        if is_historical_content:
            continue

        # Camadas do pre-commit citadas
        for m in re.finditer(r"(\d+)\s*(camadas?|layers?)", content, re.IGNORECASE):
            num = int(m.group(1))
            if num == real_layers:
                continue
            line_num = content[: m.start()].count("\n") + 1
            findings.append(
                {
                    "file": rel_norm,
                    "line": line_num,
                    "match": m.group().strip(),
                    "message": f"Camadas pre-commit: doc diz {num}, real={real_layers}",
                    "severity": "HIGH",
                }
            )

        # Skills citadas (números grandes próximos de "skills")
        for m in re.finditer(r"(\d{2})\s*(skills|skills instaladas)", content, re.IGNORECASE):
            num = int(m.group(1))
            if num == real_skills:
                continue
            if (rel_norm, num) in _SKILLS_ALLOW:
                continue
            line_num = content[: m.start()].count("\n") + 1
            findings.append(
                {
                    "file": rel_norm,
                    "line": line_num,
                    "match": m.group().strip(),
                    "message": f"Skills: doc diz {num}, real={real_skills}",
                    "severity": "MEDIUM",
                }
            )

        # Workflows citados
        for m in re.finditer(r"(\d{1,2})\s*(workflows?|workflow files)", content, re.IGNORECASE):
            num = int(m.group(1))
            if num == real_workflows:
                continue
            if (rel_norm, num) in _WORKFLOW_ALLOW:
                continue
            line_num = content[: m.start()].count("\n") + 1
            findings.append(
                {
                    "file": rel_norm,
                    "line": line_num,
                    "match": m.group().strip(),
                    "message": f"Workflows: doc diz {num}, real={real_workflows}",
                    "severity": "MEDIUM",
                }
            )

    # AGENTS.md — lições + contagem de testes (parity explícita)
    agents = ROOT / "AGENTS.md"
    if agents.exists():
        content = agents.read_text(encoding="utf-8")
        for m in re.finditer(r"(\d+)\s*li[çc]õe?s?", content, re.IGNORECASE):
            num = int(m.group(1))
            if num == real_lessons:
                continue
            line_num = content[: m.start()].count("\n") + 1
            findings.append(
                {
                    "file": "AGENTS.md",
                    "line": line_num,
                    "match": m.group().strip(),
                    "message": f"Lições: AGENTS diz {num}, real={real_lessons}",
                    "severity": "MEDIUM",
                }
            )

    return findings


def _baseline_report() -> list[str]:
    """Relatório descritivo original (frontmatter + timestamp por arquivo)."""
    from scripts.doc_utils import read_frontmatter

    lines: list[str] = []
    categories = {
        "Snapshots (Archive)": ["docs/archive/"],
        "Core Config (Live)": ["AGENTS.md", "README.md", "REGRAS.md", "LESSONS.md", "docs/changelog.md", "docs/skills.md"],
        "Reference/Docs (Timestamp)": ["docs/architecture.md", "docs/troubleshooting.md", "docs/security.md", "docs/deployment.md", "docs/deployment-staging.md", "docs/contributing.md", "docs/migration-guide.md", "docs/ROLLBACK_PROD.md", "tests/README.md"],
        "ADRs (Immutable)": ["docs/adr/"],
        "API (Auto-Generated)": ["docs/api/"],
    }
    lines.append("=" * 80)
    lines.append("ANALISE DE COERENCIA DOS .MD - BASELINE")
    lines.append("=" * 80)
    for cat, patterns in categories.items():
        lines.append(f"\n--- {cat} ---")
        for pattern in patterns:
            p = ROOT / pattern
            files = [p] if p.is_file() else sorted(p.glob("*.md"))
            for f in files:
                if not f.exists():
                    continue
                fm, body = read_frontmatter(f)
                has_fm = bool(fm)
                fm_keys = list(fm.keys()) if fm else []
                ts_match = re.search(r"> Ultima (atualizacao|revisao|snapshot): (\S+ \S+)", body)
                ts = ts_match.group(2) if ts_match else "N/A"
                truth = fm.get("truth_at") if fm else None
                rel = os.path.relpath(f, ROOT).replace("\\", "/")
                lines.append(f"  {rel}")
                lines.append(f"    Frontmatter: {'SIM' if has_fm else 'NAO'} ({', '.join(fm_keys) if fm_keys else 'vazio'})")
                lines.append(f"    Timestamp: {ts}")
                if truth:
                    lines.append(f"    truth_at: {truth}")
    return lines


def main() -> int:
    _ensure_utf8()
    parser = argparse.ArgumentParser(description="Audit de coerência dos .md (gate)")
    parser.add_argument("--check", action="store_true", help="Exit 1 se divergência HIGH/MEDIUM")
    parser.add_argument("--list", action="store_true", help="Só lista arquivos + status")
    parser.add_argument("--fix-timestamps", action="store_true", help="Re-injeta timestamps nos docs vivos")
    args = parser.parse_args()

    if args.list:
        for _, rel in _iter_live_mds():
            print(rel)
        return 0

    truth = _truth()
    print(f"TRUTH: unit={truth['test_counts'].get('unit')} schema={truth['test_counts'].get('schema')} "
          f"pages={truth['pages_count']} workflows={truth['workflows_count']} "
          f"lessons={truth['lessons_count']} layers={truth['pre_commit_layers']} skills={truth['skills_count']}")

    if args.fix_timestamps:
        from scripts.doc_utils import inject_timestamp

        changed = 0
        for fpath, rel_norm in _iter_live_mds():
            if rel_norm in ("docs/changelog.md",):
                continue
            content = fpath.read_text(encoding="utf-8")
            new_content = inject_timestamp(content, label="atualização")
            if new_content != content:
                fpath.write_text(new_content, encoding="utf-8")
                changed += 1
        print(f"\nTimestamps re-injetados em {changed} arquivo(s)")
        return 0

    print("\n" + "=" * 80)
    print("MERGE-CONFLICTS (corrupção por merge não resolvido)")
    print("=" * 80)
    conflicts = _check_merge_conflicts()
    if conflicts:
        for f in conflicts:
            print(f"  [{f['severity']}] {f['file']}:{f['line']} — {f['message']}")
    else:
        print("  Nenhum merge-conflict encontrado.")

    print("\n" + "=" * 80)
    print("DIVERGENCIAS (docs vivos vs truth)")
    print("=" * 80)
    findings = _audit_live()
    if findings:
        for f in findings:
            loc = f"{f['file']}:{f['line']}" if f["line"] else f['file']
            print(f"  [{f['severity']}] {loc} — {f['message']} {f['match']}".rstrip())
    else:
        print("  Nenhuma divergência encontrada.")

    print("\n" + "=" * 80)
    print("BASELINE (frontmatter + timestamp)")
    print("=" * 80)
    for line in _baseline_report():
        print(line)

    if args.check:
        hard = [f for f in conflicts + findings if f["severity"] == "HIGH"]
        soft = [f for f in findings if f["severity"] == "MEDIUM"]
        print(f"\n[SUMMARY] HIGH={len(hard)} MEDIUM={len(soft)}")
        if hard:
            print("[BLOCK] Divergências HIGH encontradas — correção obrigatória.")
            return 1
        if soft:
            print("[WARN] Divergências MEDIUM encontradas — revisar.")
            return 1
        print("[OK] Documentação coerente com a truth.")
    return 0


def _ensure_utf8() -> None:
    import contextlib
    import os

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
