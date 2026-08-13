"""Commits data/prices_latest.json to git (sobrescreve .gitignore com --force)."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git"] + cmd,
            capture_output=capture,
            text=capture,
            cwd=REPO_ROOT,
            timeout=30,
        )
    except Exception as e:
        return subprocess.CompletedProcess(["git"] + cmd, 1, "", str(e))


def main():
    prices_path = REPO_ROOT / "data" / "prices_latest.json"

    snapshot = None
    if prices_path.exists():
        with open(prices_path) as f:
            snapshot = json.load(f)
        total = snapshot.get("total_prices", len(snapshot) if isinstance(snapshot, list) else 0)
        print(f"Snapshot local: {total} precos")
    else:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            try:
                from services.price_repository import get_latest_prices

                prices = get_latest_prices(valid_only=True, limit=2000)
                snapshot = {
                    "collected_at": datetime.now(UTC).isoformat(),
                    "total_prices": len(prices),
                    "ingredients_found": len({p["ingredient_id"] for p in prices}),
                }
                prices_path.parent.mkdir(exist_ok=True)
                with open(prices_path, "w") as f:
                    json.dump(snapshot, f, indent=2, ensure_ascii=False)
                print(f"Snapshot do Supabase: {snapshot['total_prices']} precos")
            except Exception as e:
                print(f"Sem Supabase creds ou erro: {e}")
                print("Nada a commitar.")
                return
        else:
            print("Sem snapshot local nem Supabase creds - nada a commitar.")
            return

    _git(["config", "user.name", "github-actions[bot]"])
    _git(["config", "user.email", "github-actions[bot]@users.noreply.github.com"])

    r = _git(["add", "--force", "data/prices_latest.json"])
    if r.returncode != 0:
        print(f"Erro git add: {r.stderr or r.stdout}")
        sys.exit(1)

    r = _git(["diff", "--cached", "--exit-code", "data/prices_latest.json"])
    if r.returncode == 0:
        print("Nenhuma mudanca - nada a commitar.")
        return

    collected = snapshot.get("collected_at", datetime.now(UTC).isoformat())
    total = snapshot.get("total_prices", 0)
    ingredients = snapshot.get("ingredients_found", 0)
    msg = f"chore: snapshot prices_latest.json ({total} precos, {ingredients} ingredientes)"
    r = _git(["commit", "-m", msg])
    if r.returncode != 0:
        print(f"Erro commit: {r.stderr or r.stdout}")
        sys.exit(1)
    print(f"Commit: {msg}")

    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN", "")
    token_source = (
        "GH_PAT"
        if os.environ.get("GH_PAT")
        else ("GITHUB_TOKEN" if os.environ.get("GITHUB_TOKEN") else "nenhum")
    )
    print(f"Token de push: {token_source}")
    repo = os.environ.get("GITHUB_REPOSITORY") or _detect_repo_from_git() or ""
    ref = os.environ.get("GITHUB_REF", "HEAD")
    branch = _branch_from_ref(ref)
    if not repo:
        print("Skip push: GITHUB_REPOSITORY não definido e remote 'origin' ausente.")
        return
    if not token:
        print("Skip push: nenhum token (GH_PAT/GITHUB_TOKEN) disponível.")
        return
    # GH_PAT e necessario p/ bypass de branch protection ao pushar em master;
    # GITHUB_TOKEN padrao sofre 403. Embute o token na URL (unico metodo
    # confiavel via PAT) e faz scrub no log p/ nao vazar. [security audit]
    remote = f"https://x-access-token:{token}@github.com/{repo}.git"
    # O runner do GitHub Actions injeta o GITHUB_TOKEN via
    # `http.https://github.com/.extraheader`, que SOBRESCREVE o token embutido
    # na URL (o header leva precedencia sobre as credenciais da URL). Isso faz
    # o push autenticar como github-actions[bot] -> 403. Removemos o extraheader
    # (local) para forcar o uso do GH_PAT embutido na URL. [fix 403 actions]
    _git(["config", "--local", "http.https://github.com/.extraheader", ""])
    r = _git(["push", remote, f"HEAD:refs/heads/{branch}"], capture=True)
    if r.returncode != 0:
        safe = remote.replace(token, "***")
        err = (r.stderr or r.stdout).replace(token, "***")
        print(f"Erro push: {err} ({safe})")
        sys.exit(1)
    print("Push OK.")


def _branch_from_ref(ref: str) -> str:
    """Extrai o nome do branch de GITHUB_REF (ex.: refs/heads/master -> master)."""
    if ref.startswith("refs/heads/"):
        return ref[len("refs/heads/") :]
    if ref == "HEAD":
        return "master"
    return ref


def _detect_repo_from_git() -> str | None:
    """Detecta owner/repo via `git remote get-url origin` (ex.: git@github.com:owner/repo.git).

    Retorna None se não conseguir detectar — caller decide fallback.
    """
    r = _git(["remote", "get-url", "origin"])
    if r.returncode != 0 or not r.stdout:
        return None
    url = r.stdout.strip()
    for prefix in ("git@github.com:", "https://github.com/", "https://x-access-token:token@github.com/"):
        if url.startswith(prefix):
            path = url[len(prefix) :]
            if path.endswith(".git"):
                path = path[:-4]
            if "/" in path:
                return path
    return None


if __name__ == "__main__":
    main()
