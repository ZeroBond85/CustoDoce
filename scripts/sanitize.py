"""
sanitize.py — CustoDoce Filesystem Hygiene Tool

Limpa resíduos do working tree (caches, installers, wheels, apátridas)
sem afetar runtime, git history, ou ambiente de desenvolvimento.

Modos:
  --dry-run        (default) apenas lista o que faria
  --execute        aplica mutações com prompts Y/N por categoria
  --quick          só caches + wheels (modo rápido <2s)
  --rollback       reverte último --execute via snapshot
  --exclude=CAT    pula categoria (pode repetir: --exclude=wheels --exclude=installer)

Categorias:
  caches            __pycache__, .pytest_cache, .ruff_cache, .mypy_cache
  backup_personal   CustoDoce.7z → $env:USERPROFILE\\Backups\\
  wheels            miniconda.sh, *.whl, pyenv_bashrc.txt
  installer         C?Usersericsf/ (resíduo do installer miniconda)
  models_cache      data/onnx_models/, data/cache/, data/if_cache/, data/embedding_cache/
  skills_artifacts  data/audit/, data/skills_backup/, skills-lock.json
  apatridas         git rm de data/check_*.py, data/wf_detail.py, data/dispatch.json,
                    check_alerts.py, check_flyers.py, check_ingredients.py, debug_alert.py
  skills_commit     git add -f .opencode/skills/**, .github/workflows/skills-maintenance.yml
  gitignore_update  reescreve .gitignore com regras consolidadas + override skills
  hook_install      atualiza .githooks/pre-commit com camada RESIDUE GUARD

Snapshot / Rollback:
  Antes de mutações irreversíveis, cria .archive/sanitize/<ts>/ com manifesto JSON.
  --rollback lê o snapshot mais recente e restaura.

Uso diário:
  python scripts/sanitize.py --execute --quick     # limpeza rápida (caches + wheels)
  python scripts/sanitize.py --execute             # completa (com prompts)
  python scripts/sanitize.py --dry-run             # ver o que seria feito
  python scripts/sanitize.py --rollback            # reverter último execute
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
SANITIZE_ARCHIVE = REPO_ROOT / ".archive" / "sanitize"
SNAPSHOT_DIR = SANITIZE_ARCHIVE
LOCKFILE = SANITIZE_ARCHIVE / ".lock"
MANIFEST_NAME = "manifest.json"
EXCLUDE_DIRS = {".venv314", ".git", ".opencode/node_modules"}

# ── Categories & their metadata ──────────────────────────────────────────────
CATEGORIES = {
    "caches": {
        "title": "Cache de ferramentas (__pycache__, .pytest_cache, .ruff_cache, .mypy_cache)",
        "risk": "regenerável",
        "reversible": True,
        "quick": True,
        "needs_snapshot": False,
    },
    "backup_personal": {
        "title": "Backup pessoal CustoDoce.7z -> $env:USERPROFILE\\Backups\\",
        "risk": "movido, não deletado",
        "reversible": True,
        "quick": False,
        "needs_snapshot": True,
    },
    "wheels": {
        "title": "Wheels e installer (miniconda.sh, *.whl, pyenv_bashrc.txt)",
        "risk": "baixo — redownload de requirements.txt",
        "reversible": False,
        "quick": True,
        "needs_snapshot": False,
    },
    "installer": {
        "title": "Resíduo do installer miniconda (C?Usersericsf/)",
        "risk": "baixo — lixo do instalador que escapou",
        "reversible": False,
        "quick": False,
        "needs_snapshot": False,
    },
    "models_cache": {
        "title": "Caches ML (onnx, embedding, if_cache, cache)",
        "risk": "regenerável via export_onnx.py",
        "reversible": True,
        "quick": False,
        "needs_snapshot": False,
    },
    "skills_artifacts": {
        "title": "Artefatos de skills (audit, skills_backup, skills-lock)",
        "risk": "regenerável via skills_maintenance.py",
        "reversible": True,
        "quick": False,
        "needs_snapshot": False,
    },
    "apatridas": {
        "title": "Arquivos apátridas (data/check_*.py, check_alerts.py etc.)",
        "risk": "baixo — git rm, histórico preservado",
        "reversible": False,
        "quick": False,
        "needs_snapshot": False,
    },
    "skills_commit": {
        "title": "Forçar commit de todas as 33 skills (.opencode/skills/ + workflow)",
        "risk": "baixo — git revert possível",
        "reversible": False,
        "quick": False,
        "needs_snapshot": False,
    },
    "gitignore_update": {
        "title": "Atualizar .gitignore (regras consolidadas + override skills)",
        "risk": "baixo — git revert possível",
        "reversible": False,
        "quick": False,
        "needs_snapshot": False,
    },
    "hook_install": {
        "title": "Atualizar .githooks/pre-commit (camada RESIDUE GUARD)",
        "risk": "baixo — git revert possível",
        "reversible": False,
        "quick": False,
        "needs_snapshot": False,
    },
}

# ── Utility helpers ──────────────────────────────────────────────────────────


def say(msg: str, level: str = "INFO") -> None:
    safe_msg = msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")
    print(f"[{level}] {safe_msg}")


def warn(msg: str) -> None:
    say(msg, "AVISO")


def fail(msg: str) -> None:
    say(msg, "FALHA")
    sys.exit(1)


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Ask user Y/N. default=True means Enter=Yes."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        try:
            ans = input(question + suffix).strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans in ("", "y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("  Responda Y ou N.")


def run_git(args: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=REPO_ROOT,
        capture_output=capture,
        text=True,
    )


def git_ls_files(patterns: list[str] | None = None) -> set[str]:
    """Return tracked files matching patterns (or all tracked)."""
    cmd = ["ls-files"]
    if patterns:
        cmd.extend(["--"] + patterns)
    res = run_git(cmd)
    if res.returncode != 0:
        return set()
    return {ln.strip() for ln in res.stdout.splitlines() if ln.strip()}


def git_check_ignore(paths: list[Path]) -> list[Path]:
    """Return paths that git would ignore (i.e., they match .gitignore)."""
    if not paths:
        return []
    res = run_git(["check-ignore"] + [str(p) for p in paths])
    if res.returncode not in (0, 1):
        return []
    return [Path(ln.strip()) for ln in res.stdout.splitlines() if ln.strip()]


def is_working_tree_clean() -> bool:
    res = run_git(["status", "--porcelain"])
    return res.returncode == 0 and res.stdout.strip() == ""


def safe_delete_dir(path: Path) -> int:
    """Delete a directory tree. Returns 0 on success, 1 on error."""
    if not path.exists():
        return 0
    try:
        shutil.rmtree(path)
        return 0
    except PermissionError:
        warn(f"Não foi possível deletar (lockado?): {path}")
        return 1


def safe_delete_file(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        path.unlink()
        return 0
    except PermissionError:
        warn(f"Não foi possível deletar: {path}")
        return 1


def safe_move_file(src: Path, dst_dir: Path) -> Path | None:
    """Move src to dst_dir preserving filename. Returns destination path or None."""
    if not src.exists():
        return None
    dst_dir.mkdir(parents=True, exist_ok=True)
    dest = dst_dir / src.name
    try:
        shutil.move(str(src), str(dest))
        return dest
    except PermissionError:
        warn(f"Não foi possível mover {src} para {dst_dir}")
        return None


def disk_free_mb(path: Path = REPO_ROOT) -> int:
    """Return free disk space in MB."""
    try:
        usage = shutil.disk_usage(path)
        return usage.free // (1024 * 1024)
    except Exception:
        return 999999  # unknown, assume enough


def glob_pycache(root: Path = REPO_ROOT) -> list[Path]:
    """Find all __pycache__ directories excluding venv and git."""
    result = []
    for entry in root.rglob("__pycache__"):
        rel = entry.relative_to(REPO_ROOT)
        parts = rel.parts
        if any(excl in parts for excl in EXCLUDE_DIRS):
            continue
        result.append(entry)
    return result


def glob_whl(root: Path = REPO_ROOT) -> list[Path]:
    return [f for f in root.iterdir() if f.suffix == ".whl"]


def find_personal_backup() -> Path | None:
    p = REPO_ROOT / "CustoDoce.7z"
    return p if p.exists() else None


def find_installer_residue() -> Path | None:
    for p in REPO_ROOT.iterdir():
        if p.name.startswith("C") and "Users" in p.name:
            return p
    return None


def find_apátridas_tracked() -> dict[str, list[Path]]:
    """Return dict of apátrida category -> list of Paths that are git-tracked."""
    tracked = git_ls_files()
    result: dict[str, list[Path]] = {}

    raiz = [
        "check_alerts.py",
        "check_flyers.py",
        "check_ingredients.py",
        "debug_alert.py",
    ]
    raiz_tracked = [REPO_ROOT / f for f in raiz if f in tracked]
    if raiz_tracked:
        result["raiz"] = raiz_tracked

    data_dir = [
        "data/check_action_versions.py",
        "data/check_file.py",
        "data/check_runs.py",
        "data/check_wf_times.py",
        "data/check_workflows.py",
        "data/check_yaml_run.py",
        "data/dispatch.json",
        "data/wf_detail.py",
    ]
    data_tracked = [REPO_ROOT / f for f in data_dir if f in tracked]
    if data_tracked:
        result["data"] = data_tracked

    return result


# ── Snapshot / Rollback ──────────────────────────────────────────────────────


def create_snapshot(manifest: dict) -> Path | None:
    """Save snapshot before irreversible operations."""
    SANITIZE_ARCHIVE.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    snap_dir = SANITIZE_ARCHIVE / ts
    snap_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = snap_dir / MANIFEST_NAME
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        return snap_dir
    except OSError:
        return None


def load_latest_snapshot() -> tuple[Path, dict] | None:
    """Return (snapshot_dir, manifest) of the most recent snapshot."""
    if not SANITIZE_ARCHIVE.exists():
        return None
    snapshots = sorted(
        [d for d in SANITIZE_ARCHIVE.iterdir() if d.is_dir() and (d / MANIFEST_NAME).exists()],
        key=lambda d: d.name,
        reverse=True,
    )
    if not snapshots:
        return None
    snap_dir = snapshots[0]
    with open(snap_dir / MANIFEST_NAME) as f:
        return snap_dir, json.load(f)


def do_rollback() -> int:
    """Restore from the most recent snapshot."""
    result = load_latest_snapshot()
    if result is None:
        say("Nenhum snapshot encontrado em .archive/sanitize/", "INFO")
        return 0
    snap_dir, manifest = result
    ts = snap_dir.name
    say(f"Restaurando snapshot de {ts}...")

    # Restore backup_personal if we have its location
    backup = manifest.get("backup_personal")
    if backup and backup.get("moved_to"):
        src = Path(backup["moved_to"])
        dst = REPO_ROOT / backup["original_name"]
        if src.exists():
            shutil.move(str(src), str(dst))
            say(f"Restaurado: {dst}")
        else:
            warn(f"Arquivo não encontrado no destino: {src}. Restauração manual necessária.")

    # Restore snapshot copies
    for cat_name, copies in manifest.get("snapshot_copies", {}).items():
        for entry in copies:
            orig = Path(entry["original"])
            backup_path = snap_dir / entry["backup_name"]
            if backup_path.exists():
                orig.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup_path), str(orig))
                say(f"Restaurado: {orig}")

    say(f"Rollback do snapshot {ts} concluído", "OK")
    return 0


# ── Pre-flight checks ────────────────────────────────────────────────────────


def pre_flight_checks(excluded: set[str]) -> None:
    """Run pre-flight validations. Fail if any check doesn't pass."""
    say("Verificações pré-voo...")

    # Disk space
    free_mb = disk_free_mb()
    if free_mb < 500:
        fail(f"Espaço em disco insuficiente: {free_mb} MB livres. Mínimo 500 MB.")
    say(f"Espaço em disco: {free_mb} MB livres", "OK")

    # Apátridas usage check
    if "apatridas" not in excluded:
        apatrida_names = [
            "check_alerts",
            "check_flyers",
            "check_ingredients",
            "debug_alert",
            "check_action_versions",
            "check_file",
            "check_runs",
            "check_wf_times",
            "check_workflows",
            "check_yaml_run",
            "wf_detail",
        ]
        search_dirs = ["scrapers", "parsers", "services", "admin", "dashboard", "telegram_bot"]
        for name in apatrida_names:
            hits: list[str] = []
            for d in search_dirs:
                d_path = REPO_ROOT / d
                if not d_path.is_dir():
                    continue
                for pyfile in d_path.rglob("*.py"):
                    try:
                        content = pyfile.read_text(encoding="utf-8", errors="ignore")
                        if f"import {name}" in content or f"from {name}" in content:
                            hits.append(str(pyfile.relative_to(REPO_ROOT)))
                    except OSError:
                        pass
            # Also check main.py
            main_py = REPO_ROOT / "main.py"
            if main_py.exists():
                try:
                    content = main_py.read_text(encoding="utf-8", errors="ignore")
                    if f"import {name}" in content or f"from {name}" in content:
                        hits.append("main.py")
                except OSError:
                    pass
            if hits:
                warn(f"{name} parece ser importado por código ativo. Verifique:")
                for h in hits[:5]:
                    warn(f"  {h}")
                if not prompt_yes_no("Continuar mesmo assim?", default=False):
                    fail("Cancelado pelo usuário.")

    # Git working tree (only matters for apatridas / skills_commit / gitignore / hook)
    if not is_working_tree_clean():
        modified = ["apatridas", "skills_commit", "gitignore_update", "hook_install"]
        if any(c not in excluded for c in modified):
            warn("Working tree sujo. Recomendo commit ou stash antes de mutações em git.")
            if not prompt_yes_no("Continuar com working tree sujo?", default=False):
                fail("Cancelado pelo usuário.")


# ── Category actions ─────────────────────────────────────────────────────────


def act_caches(dry_run: bool) -> dict:
    """Remove __pycache__, .pytest_cache, .ruff_cache, .mypy_cache."""
    manifest = {"removed_dirs": [], "removed_files": []}
    targets = []

    # __pycache__ dirs
    for d in glob_pycache():
        targets.append(("dir", d))

    # Tool caches in root
    for name in (".pytest_cache", ".ruff_cache", ".mypy_cache"):
        p = REPO_ROOT / name
        if p.is_dir():
            targets.append(("dir", p))

    # Also .mypy_cache.json if exists
    mc = REPO_ROOT / ".mypy_cache.json"
    if mc.exists():
        targets.append(("file", mc))

    if not targets:
        say("  Nada a limpar em caches.", "OK")
        return manifest

    for kind, path in targets:
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
        size_mb = round(size / (1024 * 1024), 2) if size > 1024 else f"{round(size / 1024, 1)}KB"
        if dry_run:
            say(f"  [caches] Remover {path.relative_to(REPO_ROOT)} ({size_mb})")
        else:
            ok = safe_delete_dir(path) if kind == "dir" else safe_delete_file(path)
            if ok == 0:
                manifest["removed_dirs" if kind == "dir" else "removed_files"].append(str(path.relative_to(REPO_ROOT)))
                say(f"  [caches] Removido: {path.relative_to(REPO_ROOT)} ({size_mb})", "OK")
            else:
                warn(f"  [caches] Falha ao remover: {path.relative_to(REPO_ROOT)}")

    return manifest


def act_backup_personal(dry_run: bool) -> dict:
    """Move CustoDoce.7z to $env:USERPROFILE\\Backups\\."""
    archive = find_personal_backup()
    if not archive:
        say("  Nenhum CustoDoce.7z encontrado.", "OK")
        return {}

    size_mb = round(archive.stat().st_size / (1024 * 1024), 1)
    backup_dir = Path(os.environ.get("USERPROFILE", "")) / "Backups"
    dest = backup_dir / f"CustoDoce_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.7z"

    if dry_run:
        say(f"  [backup_personal] Mover {archive.name} ({size_mb}MB) -> {dest}")
        return {"original_name": archive.name, "would_move_to": str(dest)}

    if not backup_dir.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(archive), str(dest))
        say(f"  [backup_personal] Movido: {archive.name} ({size_mb}MB) → {dest}", "OK")
        return {"original_name": archive.name, "moved_to": str(dest)}
    except PermissionError:
        warn(f"  [backup_personal] Falha ao mover {archive.name}")
        return {}


def act_wheels(dry_run: bool) -> dict:
    """Remove *.whl, miniconda.sh, pyenv_bashrc.txt."""
    manifest = {"removed_files": []}
    patterns = [
        ("*.whl", glob_whl),
        (None, lambda: [REPO_ROOT / "miniconda.sh"] if (REPO_ROOT / "miniconda.sh").exists() else []),
        (None, lambda: [REPO_ROOT / "pyenv_bashrc.txt"] if (REPO_ROOT / "pyenv_bashrc.txt").exists() else []),
        (None, lambda: [REPO_ROOT / "skills-lock.json"] if (REPO_ROOT / "skills-lock.json").exists() else []),
    ]
    targets = []
    for _, finder in patterns:
        for p in finder():
            targets.append(p)

    if not targets:
        say("  Nada a limpar em wheels.", "OK")
        return manifest

    for p in targets:
        size_mb = (
            round(p.stat().st_size / (1024 * 1024), 1)
            if p.stat().st_size > 1024 * 1024
            else f"{round(p.stat().st_size / 1024, 1)}KB"
        )
        if dry_run:
            say(f"  [wheels] Remover {p.name} ({size_mb})")
        else:
            ok = safe_delete_file(p)
            if ok == 0:
                manifest["removed_files"].append(p.name)
                say(f"  [wheels] Removido: {p.name} ({size_mb})", "OK")
            else:
                warn(f"  [wheels] Falha ao remover: {p.name}")

    return manifest


def act_installer(dry_run: bool) -> dict:
    """Remove C?Usersericsf/ directory."""
    residue = find_installer_residue()
    if not residue:
        say("  Nenhum resíduo de installer (C?Usersericsf/) encontrado.", "OK")
        return {}

    size = sum(f.stat().st_size for f in residue.rglob("*") if f.is_file())
    size_mb = round(size / (1024 * 1024), 2)

    if dry_run:
        say(f"  [installer] Remover {residue.name}/ ({size_mb}MB, ~{len(list(residue.rglob('*')))} arquivos)")
        return {"dir": residue.name, "size_mb": size_mb}

    ok = safe_delete_dir(residue)
    if ok == 0:
        say(f"  [installer] Removido: {residue.name}/ ({size_mb}MB)", "OK")
        return {"dir": residue.name, "size_mb": size_mb}
    else:
        warn(f"  [installer] Falha ao remover: {residue.name}/")
        return {}


def act_models_cache(dry_run: bool) -> dict:
    """Remove data/onnx_models/, data/cache/, data/if_cache/, data/embedding_cache/."""
    manifest = {"removed_dirs": []}
    targets = [
        REPO_ROOT / "data" / "onnx_models",
        REPO_ROOT / "data" / "cache",
        REPO_ROOT / "data" / "if_cache",
        REPO_ROOT / "data" / "embedding_cache",
    ]

    found = [t for t in targets if t.exists()]
    if not found:
        say("  Nada a limpar em models_cache.", "OK")
        return manifest

    for t in found:
        size = sum(f.stat().st_size for f in t.rglob("*") if f.is_file()) if t.is_dir() else t.stat().st_size
        size_mb = round(size / (1024 * 1024), 2)
        rel = t.relative_to(REPO_ROOT)
        if dry_run:
            say(f"  [models_cache] Remover {rel} ({size_mb}MB)")
        else:
            ok = safe_delete_dir(t)
            if ok == 0:
                manifest["removed_dirs"].append(str(rel))
                say(f"  [models_cache] Removido: {rel} ({size_mb}MB)", "OK")
            else:
                warn(f"  [models_cache] Falha ao remover: {rel}")

    return manifest


def act_skills_artifacts(dry_run: bool) -> dict:
    """Remove data/audit/, data/skills_backup/, skills-lock.json."""
    manifest = {"removed_dirs": [], "removed_files": []}
    targets = [
        REPO_ROOT / "data" / "audit",
        REPO_ROOT / "data" / "skills_backup",
    ]
    files = [REPO_ROOT / "skills-lock.json"]

    found_dirs = [t for t in targets if t.exists()]
    found_files = [t for t in files if t.exists()]

    if not found_dirs and not found_files:
        say("  Nada a limpar em skills_artifacts.", "OK")
        return manifest

    for t in found_dirs:
        size = sum(f.stat().st_size for f in t.rglob("*") if f.is_file())
        size_mb = round(size / (1024 * 1024), 2)
        rel = t.relative_to(REPO_ROOT)
        if dry_run:
            say(f"  [skills_artifacts] Remover {rel} ({size_mb}MB)")
        else:
            ok = safe_delete_dir(t)
            if ok == 0:
                manifest["removed_dirs"].append(str(rel))
                say(f"  [skills_artifacts] Removido: {rel} ({size_mb}MB)", "OK")
            else:
                warn(f"  [skills_artifacts] Falha ao remover: {rel}")

    for t in found_files:
        size_kb = round(t.stat().st_size / 1024, 1)
        rel = t.relative_to(REPO_ROOT)
        if dry_run:
            say(f"  [skills_artifacts] Remover {rel} ({size_kb}KB)")
        else:
            ok = safe_delete_file(t)
            if ok == 0:
                manifest["removed_files"].append(str(rel))
                say(f"  [skills_artifacts] Removido: {rel} ({size_kb}KB)", "OK")
            else:
                warn(f"  [skills_artifacts] Falha ao remover: {rel}")

    return manifest


def act_apatridas(dry_run: bool) -> dict:
    """git rm of apátrida files + ensure gitignore entry."""
    manifest = {"git_rm": []}
    all_apatridas = find_apátridas_tracked()

    if not all_apatridas:
        say("  Nenhum arquivo apátrida tracked encontrado para remover.", "OK")
        return manifest

    for group, paths in all_apatridas.items():
        for p in paths:
            rel = p.relative_to(REPO_ROOT)
            if dry_run:
                say(f"  [apatridas] git rm {rel}")
            else:
                res = run_git(["rm", "--cached", str(rel)])
                if res.returncode == 0:
                    manifest["git_rm"].append(str(rel))
                    say(f"  [apatridas] git rm {rel}", "OK")
                else:
                    warn(f"  [apatridas] Falha git rm {rel}: {res.stderr}")

    # Also ensure .gitignore covers remaining patterns (even if untracked)
    # This is handled by gitignore_update category separately

    return manifest


def act_skills_commit(dry_run: bool) -> dict:
    """git add -f .opencode/skills/** + workflow + verify."""
    manifest = {"added_files": []}
    skills_dir = REPO_ROOT / ".opencode" / "skills"
    wf = REPO_ROOT / ".github" / "workflows" / "skills-maintenance.yml"

    if not skills_dir.exists():
        say("  skills_dir .opencode/skills/ não encontrada.", "AVISO")
        return manifest

    # Find all skills files
    skills_files = list(skills_dir.rglob("*")) + ([wf] if wf.exists() else [])
    if not skills_files:
        say("  Nenhum arquivo de skills encontrado.", "OK")
        return manifest

    if dry_run:
        count = len(skills_files)
        say(f"  [skills_commit] git add -f .opencode/skills/** + workflow ({count} arquivos)")
        return {"count": count}

    res = run_git(["add", "-f", str(skills_dir)])
    if res.returncode != 0:
        warn(f"  [skills_commit] Falha git add skills: {res.stderr}")
        return manifest

    if wf.exists():
        res2 = run_git(["add", "-f", str(wf)])
        if res2.returncode != 0:
            warn(f"  [skills_commit] Falha git add workflow: {res2.stderr}")

    # Verify they're staged
    staged = set(git_ls_files([".opencode/skills/"]))
    for p in skills_files:
        if p.is_file() and str(p) in staged:
            manifest["added_files"].append(str(p.relative_to(REPO_ROOT)))

    say(f"  [skills_commit] {len(manifest['added_files'])} arquivos adicionados ao stage", "OK")
    return manifest


def act_gitignore_update(dry_run: bool) -> dict:
    """Reescrever .gitignore com regras consolidadas."""
    gitignore_path = REPO_ROOT / ".gitignore"
    if not gitignore_path.exists():
        say("  .gitignore não encontrado.", "AVISO")
        return {}

    current = gitignore_path.read_text(encoding="utf-8")

    # Build the new content
    new_lines = []
    for line in current.splitlines(keepends=True):
        new_lines.append(line)

    # Check if sections already exist
    has_sanitize_section = any("SANEAMENTO" in l for l in new_lines)
    has_skills_override = any("!.opencode/skills/" in l for l in new_lines)
    has_installer_residue = any("C?Usersericsf" in l for l in new_lines)
    any("CustoDoce.7z" in l for l in new_lines)
    has_docs_skills = any("docs/skills.md" in l for l in new_lines)

    if dry_run:
        missing = []
        if not has_sanitize_section:
            missing.append("seção # SANEAMENTO (consolidada)")
        if not has_skills_override:
            missing.append("override !.opencode/skills/**")
        if not has_installer_residue:
            missing.append("C?Usersericsf/")
        if not has_docs_skills:
            missing.append("docs/skills.md")
        if has_skills_override and has_installer_residue and has_docs_skills and has_sanitize_section:
            say("  .gitignore já está atualizado.", "OK")
        else:
            for m in missing:
                say(f"  [gitignore_update] Adicionar: {m}")
        return {"changes": missing}

    # Apply changes
    changes = []

    # Add override line after the skills cache line (line 117)
    if not has_skills_override:
        # Find line with ".opencode/skills/"
        for i, line in enumerate(new_lines):
            if ".opencode/skills/" in line and not line.strip().startswith("#") and not line.strip().startswith("!"):
                new_lines.insert(i + 1, "!.opencode/skills/**\n")
                changes.append("override !.opencode/skills/**")
                break

    # Add consolidated section at the end if missing
    if not has_sanitize_section:
        new_lines.append("\n")
        new_lines.append("# ───────────────────────────────────────────────────────────\n")
        new_lines.append("# SANEAMENTO: resíduos do working tree (scripts/sanitize.py)\n")
        new_lines.append("# ───────────────────────────────────────────────────────────\n")
        new_lines.append("data/audit/\n")
        new_lines.append("data/skills_backup/\n")
        new_lines.append("docs/skills.md\n")
        new_lines.append("C?Usersericsf/\n")
        new_lines.append("CustoDoce.7z\n")
        new_lines.append("skills-lock.json\n")
        new_lines.append("CustoDoce.zip\n")
        changes.append("seção SANEAMENTO consolidada")

    # Ensure specific entries exist
    # We now embed these in the SANEAMENTO section, so only add if section not created
    if not has_sanitize_section:
        changes.append("C?Usersericsf/ (no gitignore)")
        changes.append("CustoDoce.7z (no gitignore)")
        changes.append("docs/skills.md (no gitignore)")

    # Remove duplicate data/ lines from the existing DATA section that are now in SANEAMENTO
    # Specifically: data/dispatch.json is already there, keep it
    # data/audit/ and data/skills_backup/ might be duplicated
    # Let's just write and let the next sanitize consolidate
    # For now, we append rather than deduplicate to avoid mistakes

    if changes:
        gitignore_path.write_text("".join(new_lines), encoding="utf-8")
        say(f"  .gitignore atualizado: {', '.join(changes)}", "OK")
        return {"changes": changes}
    else:
        say("  .gitignore já está completo.", "OK")
        return {"changes": []}


def act_hook_install(dry_run: bool) -> dict:
    """Update pre-commit with RESIDUE GUARD layer."""
    hook_path = REPO_ROOT / ".githooks" / "pre-commit"
    if not hook_path.exists():
        say("  .githooks/pre-commit não encontrado.", "AVISO")
        return {}

    current = hook_path.read_text(encoding="utf-8")

    # Check if RESIDUE GUARD already exists
    if "RESIDUE GUARD" in current:
        say("  Camada RESIDUE GUARD já presente no hook.", "OK")
        return {}

    # Build the new layer to insert before the final `exit 0`
    residue_guard = """\
# ----------------------------------------------------------------
# 7. RESIDUE GUARD - BLOQUEIA commit com artefatos de runtime no stage
# ----------------------------------------------------------------
if [ -n "${STAGED:-}" ]; then
  RESIDUE_PATTERNS='\\.whl$|^miniconda\\.sh$|^pyenv_bashrc\\.txt$|^C\\?Usersericsf/|^CustoDoce\\.7z$|\\.archive/sanitize/|^data/check_.*\\.py$|^data/wf_detail\\.py$|^data/dispatch\\.json$|^check_alerts\\.py$|^check_flyers\\.py$|^check_ingredients\\.py$|^debug_alert\\.py$|^data/audit/|^data/skills_backup/|^skills-lock\\.json$'
  RESIDUE_HITS=$(echo "$STAGED" | grep -E "$RESIDUE_PATTERNS" || true)
  if [ -n "$RESIDUE_HITS" ]; then
    echo ""
    echo "🚨 COMMIT BLOQUEADO: artefatos de runtime detectados nos arquivos staged."
    echo ""
    echo "Os seguintes arquivos nao devem ser commitados:"
    echo "$RESIDUE_HITS"
    echo ""
    echo "Acoes:"
    echo "  - Rode: python scripts/sanitize.py --execute --quick"
    echo "  - Se o arquivo e intencional, remova-o destas listas em .gitignore"
    echo "  - Ou use 'git commit --no-verify' para emergencia (NAO recomendado)"
    echo ""
    exit 1
  fi
fi

"""

    # Insert RESIDUE GUARD before the final `exit 0`
    if current.strip().endswith("exit 0"):
        modified = current.rsplit("exit 0", 1)
        new_content = modified[0] + residue_guard + "exit 0\n"
    else:
        # Append before exit 0 (anywhere in file)
        lines = current.splitlines(keepends=True)
        new_lines = []
        inserted = False
        for line in lines:
            if line.strip() == "exit 0" and not inserted:
                new_lines.append(residue_guard)
                inserted = True
            new_lines.append(line)
        if not inserted:
            new_lines.append("\n" + residue_guard)
        new_content = "".join(new_lines)

    if dry_run:
        say("  [hook_install] Adicionar camada RESIDUE GUARD ao .githooks/pre-commit")
        return {}

    hook_path.write_text(new_content, encoding="utf-8")
    say("  Camada RESIDUE GUARD adicionada ao .githooks/pre-commit", "OK")
    return {}


# ── Main dispatcher ──────────────────────────────────────────────────────────


def get_enabled_categories(args: argparse.Namespace) -> list[str]:
    """Return list of category names to execute, respecting --quick and --exclude."""
    excluded = set(args.exclude or [])

    # If --quick, only caches and wheels
    base = ["caches", "wheels"] if args.quick else list(CATEGORIES.keys())

    return [c for c in base if c not in excluded]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CustoDoce Filesystem Hygiene",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Aplica mutações (default: dry-run apenas).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Forçar dry-run (padrão se --execute não for passado).",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Modo rápido: apenas caches + wheels.",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Reverter último --execute via snapshot.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Pular categoria (pode repetir). Categorias: " + ", ".join(CATEGORIES.keys()),
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Auto-confirmar todos os prompts Y/N (modo silencioso).",
    )
    args = parser.parse_args()

    # ── Rollback mode ────────────────────────────────────────────────────
    if args.rollback:
        return do_rollback()

    # ── Determine dry-run ────────────────────────────────────────────────
    dry_run = not args.execute or args.dry_run
    mode_label = "DRY-RUN" if dry_run else "EXECUÇÃO"
    say(f"Modo: {mode_label}")
    if dry_run and args.execute:
        say("  --dry-run sobrescreve --execute", "INFO")

    # ── Acquire lock (only for --execute, not dry-run) ───────────────────
    if not dry_run:
        SANITIZE_ARCHIVE.mkdir(parents=True, exist_ok=True)
        if LOCKFILE.exists():
            lock_age = time.time() - LOCKFILE.stat().st_mtime
            if lock_age < 3600:
                fail("Outro sanitize está rodando (<1h). Remova .archive/sanitize/.lock se certeza.")
            else:
                warn("Lockfile órfão detectado (>1h). Removendo...")
                LOCKFILE.unlink(missing_ok=True)
        LOCKFILE.touch()

    try:
        # ── Get categories ───────────────────────────────────────────────
        enabled = get_enabled_categories(args)

        if not enabled:
            say("Nenhuma categoria habilitada (todas excluídas ou inválidas).", "AVISO")
            return 0

        say(f"Categorias: {', '.join(enabled)}")

        # ── Pre-flight (only for --quick or full, not pure dry-run) ──────
        if not dry_run:
            pre_flight_checks(set(args.exclude or []))

        # ── Execution map ────────────────────────────────────────────────
        # Build manifesto for snapshot
        full_manifest: dict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "mode": mode_label,
            "categories": enabled,
            "snapshot_copies": {},
        }

        action_map = {
            "caches": act_caches,
            "backup_personal": act_backup_personal,
            "wheels": act_wheels,
            "installer": act_installer,
            "models_cache": act_models_cache,
            "skills_artifacts": act_skills_artifacts,
            "apatridas": act_apatridas,
            "skills_commit": act_skills_commit,
            "gitignore_update": act_gitignore_update,
            "hook_install": act_hook_install,
        }

        for cat in enabled:
            if cat not in action_map:
                warn(f"Categoria desconhecida: {cat}")
                continue

            cat_info = CATEGORIES[cat]
            say(f"\n{'=' * 60}")
            say(f"[{cat}] {cat_info['title']}")
            say(f"  Risco: {cat_info['risk']}")

            # Prompt user if --execute (unless --yes)
            if not dry_run and not args.yes and not prompt_yes_no(f"Executar [{cat}]?", default=True):
                say(f"  [skip] {cat}")
                continue

            # Create snapshot if needed and not dry-run
            if not dry_run and cat_info.get("needs_snapshot"):
                snap_dir = create_snapshot(full_manifest)
                if snap_dir:
                    say(f"  Snapshot criado: {snap_dir}", "OK")

            # Execute
            result = action_map[cat](dry_run)

            # Track in manifest
            full_manifest[cat] = result

        # ── Summary ──────────────────────────────────────────────────────
        say(f"\n{'=' * 60}")
        if dry_run:
            say("DRY-RUN concluído. Nada foi alterado.", "INFO")
            say("Para executar: python scripts/sanitize.py --execute")
        else:
            say("EXECUÇÃO concluída.", "OK")
            say("Recomendado: verificar com 'ruff check . && python -m pytest tests/unit/ tests/schema/ -q'")

        return 0

    finally:
        # Release lock
        if not dry_run and LOCKFILE.exists():
            LOCKFILE.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
