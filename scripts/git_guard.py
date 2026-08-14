"""Remove locks git orfaos (.git/index.lock etc.) com seguranca.

Comandos git mortos no meio da escrita do index deixam `.git/index.lock`
orfaos (ex.: hook pre-commit lento estourando timeout e sendo morto pelo
shell). O guard so remove o lock se NENHUM processo git estiver rodando
(tanto no Windows quanto no WSL, pois o repo vive em /mnt/c acessado pelos
dois), evitando quebrar operacoes em andamento.

Uso:
    python scripts/git_guard.py          # remove locks orfaos
    python scripts/git_guard.py --check  # apenas reporta (exit 1 se houver)
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

LOCK_NAMES = (
    "index.lock",
    "HEAD.lock",
    "shallow.lock",
    "config.lock",
    "packed-refs.lock",
    "refs/remotes/origin.lock",
)


def _repo_root() -> Path:
    cur = Path.cwd().resolve()
    for p in (cur, *cur.parents):
        if (p / ".git").exists():
            return p
    sys.exit("Sem repositorio git neste diretorio")


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception:
        return None


def _git_running() -> bool:
    # Windows
    if os.name == "nt":
        r = _run(["tasklist", "/FI", "IMAGENAME eq git.exe", "/FO", "CSV", "/NH"])
        # tasklist retorna rc=0 com a mensagem "nenhuma tarefa" quando NAO ha
        # processos; so considera rodando se o output contiver "git.exe".
        if r and r.returncode == 0 and "git.exe" in r.stdout.lower():
            return True
    # Linux/WSL
    if sys.platform.startswith("linux"):
        r = _run(["pgrep", "-x", "git"])
        if r and r.returncode == 0 and r.stdout.strip():
            return True
    # Cross-environment: checa o outro lado tb (repo acessado por ambos)
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if wsl:
        if os.name == "nt":
            r = _run([wsl, "-e", "bash", "-lc", "pgrep -x git"])
            if r and r.returncode == 0 and r.stdout.strip():
                return True
        else:
            r = _run(["tasklist.exe", "/FI", "IMAGENAME eq git.exe", "/FO", "CSV", "/NH"])
            if r and r.returncode == 0 and "git.exe" in r.stdout.lower():
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="apenas reporta, nao remove")
    args = ap.parse_args()
    root = _repo_root()
    git_dir = root / ".git"
    removed = []
    present = 0
    for name in LOCK_NAMES:
        lock = git_dir / name
        if lock.exists():
            present += 1
            if args.check:
                print(f"[git-guard] LOCK PRESENTE: {lock}")
                continue
            if _git_running():
                print(f"[git-guard] SKIP (git rodando): {lock}")
            else:
                try:
                    lock.unlink()
                    removed.append(str(lock))
                    print(f"[git-guard] lock orfao removido: {lock}")
                except OSError as e:
                    print(f"[git-guard] erro ao remover {lock}: {e}")
    if removed:
        print(f"[git-guard] removidos: {len(removed)}")
    if present and not removed:
        print(f"[git-guard] {present} lock(s) presentes; git em execucao ou --check")
    if args.check and present:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
