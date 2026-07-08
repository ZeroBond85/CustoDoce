"""
Sync MD Catch-up — one-shot catch-up for archive docs.

Alinha o `truth_at` do frontmatter com a verdade calculada do projeto,
sem produzir marcadores incrementais "(era N)". Roda UMA ÚNICA VEZ.

Política aplicada:
  - SNAPSHOT_FROZEN        → bypass total (audit pontual)
  - SNAPSHOT_REFERENCE_LIVE → alinha truth_at (Raio-X completo)
  - SNAPSHOT_DERIVED_LIVE   → alinha + bump version (Resumido)

Após catch-up, o regime normal (apply_intelligent) passa a operar de
forma segura sem corromper histórico já registrado em "(era X)".

Uso:
    python scripts/sync_md_catchup.py --dry-run
    python scripts/sync_md_catchup.py --apply

Exit codes:
    0 = nenhum catch-up necessário
    1 = catch-up necessário (--dry-run)
    2 = erro
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.doc_sync_policy import DocPolicy, policy_for  # noqa: E402
from scripts.doc_utils import read_frontmatter, write_frontmatter  # noqa: E402

_ARCHIVE_DIR = _ROOT / "docs" / "archive"


def _project_truth() -> dict[str, int | str]:
    """Verdade canônica do projeto (calculada em runtime).

    Os snapshots do archive precisam saber:
      - tests_total: total de testes unit + schema
      - pages_count: navegação ativa do dashboard
      - python_version: regra 10 do AGENTS.md (Python 3.14+)

    Origem única: `_build_agents_state()` de sync_docs.py — compartilhado
    com AGENTS.md e demais sincronizações.
    """
    from scripts.sync_docs import _build_agents_state

    state = _build_agents_state()
    test_counts: dict = state.get("test_counts", {}) or {}
    real_total = int(test_counts.get("unit", 0)) + int(test_counts.get("schema", 0))
    real_pages = int(state.get("pages_count", 0))
    return {
        "tests_total": real_total,
        "pages_count": real_pages,
        "python_version": "3.14.6",
    }


def _bump_version(cur: str) -> str:
    try:
        major, minor, patch = (int(p) for p in cur.split("."))
        return f"{major}.{minor}.{patch + 1}"
    except Exception:
        return "0.0.1"


def _process_doc(md_file: Path, dry_run: bool) -> dict | None:
    """Processa um único arquivo de archive. Retorna change dict ou None."""
    rel = md_file.relative_to(_ROOT)
    policy = policy_for(rel)

    if policy == DocPolicy.SNAPSHOT_FROZEN:
        print(f"  [SKIP-FROZEN] {rel}: data-anchored, bypass catch-up")
        return None

    fm, body = read_frontmatter(md_file)
    if not fm:
        print(f"  [SKIP] {rel}: sem frontmatter — não candidato a catch-up")
        return None

    truth_at = dict(fm.get("truth_at") or {})
    new_truth_at = dict(truth_at)
    project = _project_truth()

    diffs: list[str] = []
    for key, real in project.items():
        prev = truth_at.get(key)
        if prev != real:
            new_truth_at[key] = real
            diffs.append(f"{key}: {prev!r} -> {real!r}")

    cur_version = str(fm.get("current_version", "0.0.0"))
    needs_version_bump = cur_version == "0.0.0"

    if not diffs and not needs_version_bump:
        print(f"  [OK] {rel}: já alinhado (truth_at + current_version)")
        return None

    bumped = _bump_version(cur_version) if needs_version_bump else cur_version
    change = {
        "file": str(rel),
        "policy": policy.value,
        "diffs": diffs,
        "old_version": cur_version,
        "new_version": bumped,
    }

    if dry_run:
        print(f"  [WOULD CATCH-UP] {rel} (policy={policy.value})")
        for d in diffs:
            print(f"    - {d}")
        if needs_version_bump:
            print(f"    - current_version: {cur_version} -> {bumped}")
        return change

    fm["truth_at"] = new_truth_at
    if needs_version_bump:
        fm["current_version"] = bumped
    write_frontmatter(md_file, fm, body)
    print(f"  [OK] {rel} aligned (policy={policy.value}):")
    for d in diffs:
        print(f"    - {d}")
    if needs_version_bump:
        print(f"    - current_version: {cur_version} -> {bumped}")
    return change


def catchup_archive(dry_run: bool = True) -> list[dict]:
    changes: list[dict] = []
    if not _ARCHIVE_DIR.exists():
        print("[ERR] docs/archive/ não existe")
        return changes

    for md_file in sorted(_ARCHIVE_DIR.glob("*.md")):
        change = _process_doc(md_file, dry_run=dry_run)
        if change:
            changes.append(change)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Catch-up one-shot for docs/archive/*.md")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing (default)")
    parser.add_argument("--apply", action="store_true", help="Apply catch-up writes")
    args = parser.parse_args()
    dry_run = not args.apply

    print(f"=== Sync MD Catchup ({'DRY-RUN' if dry_run else 'APPLY'}) ===")
    print(f"Archive dir: {_ARCHIVE_DIR}")
    print()

    if not _ARCHIVE_DIR.exists():
        print("[ERR] docs/archive/ não existe")
        return 2

    changes = catchup_archive(dry_run=dry_run)
    print()

    if not changes:
        print("[OK] Nenhum catch-up necessário — truth_at já alinhado.")
        return 0

    if dry_run:
        print(f"[NEEDS] {len(changes)} doc(s) precisam catch-up. Rode com --apply.")
        return 1

    print(f"[DONE] {len(changes)} doc(s) atualizadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
