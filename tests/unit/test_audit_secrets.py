# ruff: noqa: S603, S607 — bandit safety rules are false positives for test subprocess calls

"""
test_audit_secrets.py — Testa o escopo --since do audit_secrets.

Valida que:
  - scan_tracked_files() sem --since varre o repo inteiro
  - scan_tracked_files(since=N) restringe a arquivos alterados recentemente
  - segredos em commits antigos sao ignorados pelo escopo --since
  - segredos em arquivos novos (nao rastreados) sao detectados pelo --since
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_secrets.py"


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Cria um repo git temporario com 100 arquivos limpos + 1 commit inicial."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    # 100 arquivos limpos no commit inicial
    for i in range(100):
        (repo / f"file_{i:03d}.txt").write_text(f"conteudo limpo {i}\n", encoding="utf-8")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", "init 100 arquivos limpos")
    return repo


def _add_secret_commit(repo: Path, filename: str, secret: str, msg: str) -> None:
    (repo / filename).write_text(f"token={secret}\n", encoding="utf-8")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", msg)


def test_scan_full_detects_old_secret(git_repo: Path) -> None:
    """Sem --since, segredo em commit antigo e detectado."""
    _add_secret_commit(git_repo, "old_secret.txt", "sk-abcdefghijklmnopqrstuvwxyz1234", "secret antigo")
    out = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--json"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "sk-" in out.stdout


def test_scan_since_ignores_old_secret(git_repo: Path) -> None:
    """Com --since 1, segredo em commit antigo (nao nos ultimos 1 commit) e ignorado.

    Cenario: adiciona segredo no commit 2, depois um commit limpo no commit 3.
    --since 1 escaneia so o commit 3 (limpo) -> segredo nao aparece.
    """
    _add_secret_commit(git_repo, "old_secret.txt", "sk-abcdefghijklmnopqrstuvwxyz1234", "secret antigo")
    (git_repo / "clean.txt").write_text("arquivo limpo recente\n", encoding="utf-8")
    _run_git(git_repo, "add", "-A")
    _run_git(git_repo, "commit", "-q", "-m", "commit limpo recente")
    out = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--since", "1", "--json"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "sk-" not in out.stdout


def test_scan_since_detects_recent_secret(git_repo: Path) -> None:
    """Com --since 1, segredo adicionado no commit mais recente e detectado."""
    _add_secret_commit(git_repo, "recent_secret.txt", "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234", "secret recente")
    out = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--since", "1", "--json"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "gsk_" in out.stdout


def test_scan_since_detects_new_untracked_file(git_repo: Path) -> None:
    """Arquivo novo nao rastreado com segredo e detectado pelo --since."""
    (git_repo / "nova.txt").write_text("hf_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234\n", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--since", "1", "--json"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "hf_" in out.stdout


def test_scan_since_clean_repo_passes(git_repo: Path) -> None:
    """Repo limpo com --since nao reporta segredos."""
    out = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--since", "1", "--json"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "sk-" not in out.stdout
    assert "gsk_" not in out.stdout
